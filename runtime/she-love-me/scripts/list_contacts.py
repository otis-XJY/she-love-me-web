"""
list_contacts.py - 列出微信联系人及消息数量

从解密后的 SQLite 数据库读取：
  - contact/contact.db -> contact 表 (username, nick_name, remark)
  - message/message_N.db -> Name2Id + Msg_* 表计数
"""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

# Windows 控制台 UTF-8 输出
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def get_display_name(row):
    username, nick_name, remark = row
    return remark or nick_name or username


def json_error(message, **extra):
    payload = {"error": message, **extra}
    print(json.dumps(payload, ensure_ascii=False))


def open_checked_db(path):
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        result = conn.execute("PRAGMA quick_check").fetchone()
        if not result or str(result[0]).lower() != "ok":
            raise sqlite3.DatabaseError(f"quick_check failed: {result[0] if result else 'empty result'}")
        return conn
    except sqlite3.DatabaseError as exc:
        raise RuntimeError(
            "联系人数据库损坏或解密不完整。请重新执行“开始读取联系人”；如果仍失败，关闭微信并用管理员权限重新启动本地服务后再试。"
        ) from exc


def load_contacts(decrypted_dir):
    contact_db = os.path.join(decrypted_dir, "contact", "contact.db")
    if not os.path.exists(contact_db):
        print(f"[!] 找不到联系人数据库: {contact_db}", file=sys.stderr)
        return []

    contacts = []
    conn = open_checked_db(contact_db)
    try:
        try:
            rows = conn.execute(
                "SELECT username, nick_name, remark FROM contact WHERE username NOT LIKE '%@chatroom'"
            ).fetchall()
        except sqlite3.OperationalError as exc:
            json_error(
                "联系人数据库表结构与当前工具预期不一致，常见于微信大版本升级后。请更新 "
                "runtime/she-love-me/vendor/wechat-decrypt（或重新运行「环境检查」以拉取最新解密工具）；"
                "若仍失败，请在 issue 中附上微信版本与完整报错。",
                code="CONTACT_SCHEMA_MISMATCH",
                detail=str(exc),
            )
            sys.exit(2)
        for row in rows:
            username, nick_name, remark = row
            display = remark or nick_name or username
            # 过滤掉公众号和系统账号
            if username.startswith("gh_") or username in ("filehelper", "newsapp", "weixin", "fmessage"):
                continue
            contacts.append({
                "username": username,
                "nick_name": nick_name or "",
                "remark": remark or "",
                "display_name": display,
                "message_count": 0,
            })
    finally:
        conn.close()

    print(f"[进度] 通讯录已载入 {len(contacts)} 人（待统计各消息库中的条数）", file=sys.stderr, flush=True)

    return contacts


def count_messages(decrypted_dir, contacts):
    """扫描 message/message_N.db 文件，统计每个联系人的消息数"""
    username_to_idx = {c["username"]: i for i, c in enumerate(contacts)}
    msg_dir = os.path.join(decrypted_dir, "message")
    total_contacts = len(contacts)
    if total_contacts == 0:
        return
    if not os.path.exists(msg_dir):
        print(f"[进度] 联系人 0/{total_contacts}", file=sys.stderr, flush=True)
        return

    msg_dbs = sorted([
        f for f in os.listdir(msg_dir)
        if re.match(r"message_\d+\.db$", f)
    ])

    print(f"[进度] 联系人 0/{total_contacts}", file=sys.stderr, flush=True)

    for db_idx, db_file in enumerate(msg_dbs, start=1):
        db_path = os.path.join(msg_dir, db_file)
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        except Exception:
            with_msg = sum(1 for c in contacts if c.get("message_count", 0) > 0)
            print(f"[进度] 联系人 {with_msg}/{total_contacts}", file=sys.stderr, flush=True)
            continue
        try:
            try:
                checked = conn.execute("PRAGMA quick_check").fetchone()
                db_ok = bool(checked and str(checked[0]).lower() == "ok")
            except sqlite3.DatabaseError:
                db_ok = False
            if not db_ok:
                print(f"[!] 跳过损坏消息库: {db_path}", file=sys.stderr)
            else:
                try:
                    id_rows = conn.execute("SELECT user_name FROM Name2Id").fetchall()
                except sqlite3.OperationalError:
                    id_rows = []
                for (user_name,) in id_rows:
                    if not user_name or user_name not in username_to_idx:
                        continue
                    table_hash = hashlib.md5(user_name.encode()).hexdigest()
                    table_name = f"Msg_{table_hash}"
                    try:
                        count = conn.execute(f"SELECT COUNT(*) FROM [{table_name}]").fetchone()[0]
                        contacts[username_to_idx[user_name]]["message_count"] += count
                    except sqlite3.OperationalError:
                        pass
        finally:
            conn.close()
        with_msg = sum(1 for c in contacts if c.get("message_count", 0) > 0)
        print(f"[进度] 联系人 {with_msg}/{total_contacts}", file=sys.stderr, flush=True)


def main():
    parser = argparse.ArgumentParser(description="列出微信联系人")
    parser.add_argument("--decrypted-dir", required=True, help="解密数据库目录")
    args = parser.parse_args()

    decrypted_dir = os.path.abspath(args.decrypted_dir)
    if not os.path.exists(decrypted_dir):
        print(json.dumps({"error": f"目录不存在: {decrypted_dir}"}))
        sys.exit(1)

    try:
        contacts = load_contacts(decrypted_dir)
    except RuntimeError as exc:
        contact_db = Path(decrypted_dir) / "contact" / "contact.db"
        json_error(str(exc), code="CONTACT_DB_CORRUPT", path=str(contact_db))
        sys.exit(2)

    if not contacts:
        print(json.dumps({"error": "未找到联系人数据"}, ensure_ascii=False))
        sys.exit(1)

    count_messages(decrypted_dir, contacts)

    with_msg = [c for c in contacts if c["message_count"] > 0]
    print(f"[进度] 统计完成：{len(with_msg)} 个联系人有消息记录", file=sys.stderr, flush=True)
    top_preview = sorted(with_msg, key=lambda c: c["message_count"], reverse=True)[:15]
    for i, c in enumerate(top_preview, 1):
        print(
            f"[进度] Top {i}: {c['display_name']} · {c['message_count']} 条",
            file=sys.stderr,
            flush=True,
        )

    # 按消息数量排序，过滤掉 0 消息的
    contacts = [c for c in contacts if c["message_count"] > 0]
    contacts.sort(key=lambda c: c["message_count"], reverse=True)

    print(json.dumps(contacts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
