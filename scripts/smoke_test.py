"""
后端端到端冒烟测试

跑通两条主要路径，不调用需要 GPU 的检索接口（--with-ai 才跑那些）：

  路径一 从大纲创建 → 章节改名（验证大纲同步）→ 编辑 PRECHA → 手写正文
                    → 版本历史 → 回滚 → 重排章节 → 导出
  路径二 从 IDEA 创建 → 新建 CHA1/CHA2 → 验证设定复制 → 验证叙述范围隔离

用法：
  python scripts/smoke_test.py             # 不调 AI，快
  python scripts/smoke_test.py --with-ai   # 额外测 PRECHA 自动提取和上下文组装
"""
import os
import sys
import json
import argparse

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    mark = "OK  " if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if detail else ""))
    return cond


def api(client, method, path, **kw):
    resp = getattr(client, method)(path, **kw)
    body = None
    try:
        body = resp.get_json()
    except Exception:
        pass
    return resp.status_code, body


def main(with_ai=False):
    from app import create_app
    from database import db, Idea, Outline, Project, Chapter, StoryEntity, Revision

    app = create_app()
    c = app.test_client()

    print("=" * 70)
    print("  后端冒烟测试")
    print("=" * 70)

    created_projects = []
    created_outlines = []

    # ---------------------------------------------------------------
    print("\n[1] 只读接口")
    for path in ("/api/projects", "/api/ideas", "/api/outlines",
                 "/api/categories", "/api/libraries"):
        code, _ = api(c, "get", path)
        check(f"GET {path}", code == 200, f"HTTP {code}")

    # 迁移完整性：老大纲也都该有归属作品（否则创作界面进不去）
    with app.app_context():
        orphans = [o.id for o in Outline.query.all() if not o.project_id]
        n_outlines = Outline.query.count()
    check("存量大纲都有归属作品", not orphans,
          f"无归属 {orphans}" if orphans else f"{n_outlines} 个大纲")

    # ---------------------------------------------------------------
    print("\n[2] 路径一：从大纲创建作品")
    # 测试用的大纲自己造 —— 后面要改名、写正文、重排，绝不能拿用户的真稿开刀
    parsed = {
        "title": "冒烟测试·大纲",
        "synopsis": "冒烟测试专用，测完即删。",
        "themes": "测试",
        "parsed_ok": True,
        "chapters": [
            {"chapter_number": i, "title": f"冒烟CHA{i}", "sort_key": i * 1000.0,
             "plan_scene": f"场景{i}", "plan_events": f"事件{i}",
             "plan_emotion": f"情绪{i}", "plan_settings": f"设定{i}",
             "plan_notes": ""}
            for i in range(1, 4)
        ],
    }
    code, body = api(c, "post", "/api/outlines/save",
                     json={"title": parsed["title"],
                           "content": "# 冒烟测试·大纲\n\n## 章节规划\n",
                           "parsed": parsed})
    ok = check("POST /api/outlines/save（自建测试大纲）", code == 200,
               f"HTTP {code}")
    if not ok:
        return report()
    outline_id = body["id"]
    created_outlines.append(outline_id)
    project_id = body["project_id"]
    created_projects.append(project_id)
    check("保存大纲时一并建好作品与章节",
          len(body.get("chapters", [])) == 3,
          f"{len(body.get('chapters', []))} 章")

    # 同一个大纲再建一次作品应该复用而不是复制一套 ——
    # 否则「改章节名，大纲页跟着变」这条保证就不成立了
    code, body2 = api(c, "post", "/api/projects",
                      json={"source_type": "outline", "outline_id": outline_id})
    check("一个大纲只对应一个作品", code == 200
          and body2.get("reused") is True
          and body2["project"]["id"] == project_id,
          f"reused={body2.get('reused')}" if code == 200 else f"HTTP {code}")

    code, body = api(c, "get", f"/api/projects/{project_id}")
    chapters = body.get("chapters", [])
    check("GET /api/projects/<id> 返回章节列表",
          code == 200 and len(chapters) == 3, f"{len(chapters)} 章")

    ch = chapters[0]
    code, body = api(c, "get", f"/api/chapters/{ch['id']}")
    detail = body or {}
    check("GET /api/chapters/<id> 含计划字段",
          code == 200 and detail.get("plan_scene") == "场景1")
    check("GET /api/chapters/<id> 含拆开的 PRECHA 字段",
          all(k in detail for k in
              ("precha_time", "precha_place", "precha_chars", "precha_cause",
               "precha_process", "precha_result", "precha_media")))
    check("GET /api/chapters/<id> 含越界自检", "audit" in detail)

    # ---------------------------------------------------------------
    print("\n[3] 改章节名 → 大纲页是否同步")
    new_title = "冒烟测试改名·滤网"
    code, body = api(c, "put", f"/api/chapters/{ch['id']}",
                     json={"title": new_title})
    check("PUT /api/chapters/<id> 改名", code == 200, f"HTTP {code}")

    code, body = api(c, "get", f"/api/outlines/{outline_id}")
    outline_chapters = (body or {}).get("chapters", [])
    synced = any(oc["id"] == ch["id"] and oc["title"] == new_title
                 for oc in outline_chapters)
    check("大纲页看到的章节名同步变了", synced,
          "共用同一行 Chapter，所以不需要双向同步")

    # ---------------------------------------------------------------
    print("\n[4] PRECHA 表单编辑")
    precha_payload = {
        "precha_time": "2127年11月14日清晨",
        "precha_place": "维修间",
        "precha_chars": "汪远、老贺",
        "precha_cause": "冒烟测试起因",
        "precha_process": "冒烟测试经过",
        "precha_result": "冒烟测试结果",
        "precha_media": "示波器",
    }
    code, body = api(c, "put", f"/api/chapters/{ch['id']}", json=precha_payload)
    saved = body.get("chapter", {}) if body else {}
    check("PUT PRECHA 七字段", code == 200
          and all(saved.get(k) == v for k, v in precha_payload.items()))
    check("手改后 precha_auto 置为 False", saved.get("precha_auto") is False,
          "之后不会被自动提取覆盖")

    # ---------------------------------------------------------------
    print("\n[5] 手写正文 + 版本历史 + 回滚")
    v1 = "这是冒烟测试写下的第一版正文。十七块五，不甜。"
    v2 = "这是冒烟测试写下的第二版正文，比第一版长一些，用来验证回滚。"

    code, body = api(c, "put", f"/api/chapters/{ch['id']}", json={"content": v1})
    check("PUT 正文 v1", code == 200)
    code, body = api(c, "put", f"/api/chapters/{ch['id']}", json={"content": v2})
    saved = body.get("chapter", {}) if body else {}
    check("PUT 正文 v2", code == 200)
    check("字数自动重算", saved.get("word_count", 0) > 0,
          f"{saved.get('word_count')} 字")
    check("状态自动从 planned 变 draft", saved.get("status") == "draft")

    code, revs = api(c, "get", f"/api/chapters/{ch['id']}/revisions")
    check("GET 版本历史", code == 200 and len(revs) >= 1,
          f"{len(revs)} 个版本")

    if revs:
        target = revs[-1]["version_no"]
        code, body = api(c, "post", f"/api/chapters/{ch['id']}/revert/{target}")
        reverted = body.get("chapter", {}) if body else {}
        check(f"回滚到 v{target}", code == 200)
        code, revs2 = api(c, "get", f"/api/chapters/{ch['id']}/revisions")
        check("回滚本身也留了一版（可再滚回来）", len(revs2) > len(revs),
              f"{len(revs)} → {len(revs2)}")

    # ---------------------------------------------------------------
    print("\n[6] 章节重排")
    code, body = api(c, "get", f"/api/projects/{project_id}/chapters")
    ids = [x["id"] for x in (body or [])]
    if len(ids) >= 3:
        reordered = [ids[1], ids[0]] + ids[2:]
        code, body = api(c, "put", f"/api/projects/{project_id}/reorder",
                         json={"order": reordered})
        result = (body or {}).get("chapters", [])
        check("PUT 重排章节", code == 200, f"HTTP {code}")
        check("章号重新压实为 1..n",
              [x["chapter_number"] for x in result] == list(range(1, len(result) + 1)))
        check("顺序按提交的来", [x["id"] for x in result] == reordered)
        # 排回去
        api(c, "put", f"/api/projects/{project_id}/reorder", json={"order": ids})
    else:
        check("章节数够做重排测试", False, f"只有 {len(ids)} 章")

    # ---------------------------------------------------------------
    print("\n[7] 路径二：从 IDEA 创建作品")
    with app.app_context():
        idea = (Idea.query.join(StoryEntity, StoryEntity.idea_id == Idea.id)
                .order_by(Idea.id).first())
        if idea is None:
            idea = Idea.query.order_by(Idea.id).first()
        idea_id = idea.id if idea else None
        n_idea_entities = (StoryEntity.query.filter_by(idea_id=idea_id).count()
                           if idea_id else 0)

    if check("存在可用的创意", idea_id is not None):
        code, body = api(c, "post", "/api/projects",
                         json={"source_type": "idea", "idea_id": idea_id,
                               "title": "冒烟测试·从创意"})
        ok = check("POST /api/projects (from_idea)", code == 200, f"HTTP {code}")
        if ok:
            p2 = body["project"]
            created_projects.append(p2["id"])
            check("空作品，没有章节", p2["chapter_count"] == 0)
            check("人物/世界观已从创意复制过来",
                  len(p2.get("entities", [])) == n_idea_entities,
                  f"复制 {len(p2.get('entities', []))} 条 / 创意有 {n_idea_entities} 条")

            # 新建两章
            for i, title in enumerate(["冒烟第一章", "冒烟第二章"], 1):
                code, body = api(c, "post", f"/api/projects/{p2['id']}/chapters",
                                 json={"title": title, "auto_precha": with_ai})
                created = (body or {}).get("chapter", {})
                check(f"新建 CHA{i}", code == 200 and created.get("chapter_number") == i,
                      f"HTTP {code}")
                if i == 1 and code == 200:
                    check("首章 PRECHA 标记为 /",
                          created.get("precha_name") == "/" or not with_ai)
                    api(c, "put", f"/api/chapters/{created['id']}",
                        json={"content": "第一章的正文，用来给第二章生成 PRECHA。"})

            # 叙述范围隔离 —— 自建测试数据，不依赖库里恰好有结构化条目
            code, body = api(c, "post", f"/api/projects/{p2['id']}/entities",
                             json={"kind": "character", "name": "冒烟·贯穿人物",
                                   "summary": "全书都在"})
            always = (body or {}).get("entity", {})
            code, body = api(c, "post", f"/api/projects/{p2['id']}/entities",
                             json={"kind": "character", "name": "冒烟·后期人物",
                                   "summary": "第5章才出场",
                                   "first_appear_chapter": 5})
            later = (body or {}).get("entity", {})
            check("POST 作品设定条目", bool(always.get("id")) and bool(later.get("id")))

            with app.app_context():
                from services import context_builder as cb
                vis1 = [e.id for e in cb.visible_entities(p2["id"], 1)[0]]
                vis5 = [e.id for e in cb.visible_entities(p2["id"], 5)[0]]
                check("first_appear_chapter=5 的条目在 CHA1 被屏蔽",
                      later["id"] not in vis1, "防叙述越界")
                check("到 CHA5 时才可见", later["id"] in vis5)
                check("没设出场章的条目一直可见",
                      always["id"] in vis1 and always["id"] in vis5)

    # ---------------------------------------------------------------
    print("\n[8] 导出")
    code, body = api(c, "post", f"/api/writing/export/{project_id}",
                     json={"only_completed": False})
    check("POST 导出 Markdown", code == 200, f"HTTP {code}")
    if code == 200:
        check("导出内容非空", len((body or {}).get("full_text", "")) > 0,
              f"{body.get('chapter_count')} 章 / {body.get('word_count')} 字")

    # ---------------------------------------------------------------
    if with_ai:
        print("\n[9] AI 相关（需要 API + GPU）")
        code, body = api(c, "get", f"/api/chapters/{ch['id']}/context")
        ok = check("GET 上下文预览", code == 200, f"HTTP {code}")
        if ok:
            snap = (body or {}).get("snapshot", {})
            check("章节计划只给到当前章",
                  snap.get("plan_upto") == ch["chapter_number"],
                  f"plan_upto={snap.get('plan_upto')}, 当前章={ch['chapter_number']}")
            check("记录了注入的设定数", "entity_count" in snap,
                  f"{snap.get('entity_count')} 条，屏蔽 {snap.get('hidden_future_entities')} 条")
            check("记录了检索命中", snap.get("rag_hits", 0) >= 0,
                  f"{snap.get('rag_hits')} 条，来自 {len(snap.get('rag_files', []))} 个文件")

    # ---------------------------------------------------------------
    print("\n[清理] 删除测试数据")
    for pid in created_projects:
        code, _ = api(c, "delete", f"/api/projects/{pid}")
        check(f"DELETE /api/projects/{pid}", code == 200)

    for oid in created_outlines:
        code, _ = api(c, "delete", f"/api/outlines/{oid}")
        check(f"DELETE /api/outlines/{oid}", code == 200)

    # 测试数据全在自建作品里，用户原有的创意/大纲/作品一个字节都没动过
    with app.app_context():
        left = (Chapter.query.filter(Chapter.title.like("冒烟%")).count()
                + Project.query.filter(Project.title.like("冒烟%")).count()
                + Outline.query.filter(Outline.title.like("冒烟%")).count())
    check("没在用户数据里留下痕迹", left == 0, f"残留 {left} 条")

    return report()


def report():
    print("\n" + "=" * 70)
    print(f"  通过 {len(PASS)} / {len(PASS) + len(FAIL)}")
    if FAIL:
        print("  失败项：")
        for f in FAIL:
            print(f"    - {f}")
    print("=" * 70)
    return 0 if not FAIL else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="后端冒烟测试")
    parser.add_argument("--with-ai", action="store_true",
                        help="额外测试需要调用 AI / 向量库的接口")
    args = parser.parse_args()
    sys.exit(main(with_ai=args.with_ai))
