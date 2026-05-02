#!/usr/bin/env python3
"""飞书知识库 Skill 后端脚本 — 通过子命令提供所有 API 调用能力。"""

import argparse
import getpass
import json
import os
import sys
import time

from dotenv import load_dotenv

KEYRING_SERVICE = "feishu-wiki-skill"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_FILE = os.path.join(SCRIPT_DIR, ".feishu_token")


def output_json(data: dict | list) -> None:
    """输出 JSON 到 stdout。"""
    print(json.dumps(data, ensure_ascii=False, indent=2))


def output_error(error_type: str, message: str, code: int | None = None) -> None:
    """输出错误 JSON 到 stderr 并退出。"""
    err = {"error": error_type, "message": message}
    if code is not None:
        err["code"] = code
    print(json.dumps(err, ensure_ascii=False), file=sys.stderr)
    sys.exit(1)


_keyring_available: bool | None = None


def _check_keyring() -> bool:
    global _keyring_available
    if _keyring_available is not None:
        return _keyring_available
    try:
        import keyring
        keyring.get_password(KEYRING_SERVICE, "__probe__")
        _keyring_available = True
    except Exception:
        _keyring_available = False
        print("警告: keyring 不可用，将使用文件存储（明文）", file=sys.stderr)
    return _keyring_available


def _set_credential(key: str, value: str) -> None:
    if _check_keyring():
        import keyring
        keyring.set_password(KEYRING_SERVICE, key, value)
    else:
        data = _load_token_file()
        data[key] = value
        _save_token_file(data)


def _get_credential(key: str) -> str | None:
    if _check_keyring():
        import keyring
        return keyring.get_password(KEYRING_SERVICE, key)
    data = _load_token_file()
    if key in data:
        return data[key]
    load_dotenv(os.path.join(SCRIPT_DIR, ".env"))
    env_map = {"app_id": "FEISHU_APP_ID", "app_secret": "FEISHU_APP_SECRET"}
    if key in env_map:
        return os.getenv(env_map[key])
    return None


def _delete_credential(key: str) -> None:
    if _check_keyring():
        import keyring
        try:
            keyring.delete_password(KEYRING_SERVICE, key)
        except keyring.errors.PasswordDeleteError:
            pass
    else:
        data = _load_token_file()
        data.pop(key, None)
        _save_token_file(data)


def _load_token_file() -> dict:
    if not os.path.exists(TOKEN_FILE):
        return {}
    with open(TOKEN_FILE) as f:
        return json.load(f)


def _save_token_file(data: dict) -> None:
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass


def get_app_credentials() -> tuple[str, str]:
    app_id = _get_credential("app_id")
    app_secret = _get_credential("app_secret")
    if not app_id or not app_secret:
        output_error("credentials_missing", "请先执行 init 命令配置 APP_ID 和 APP_SECRET")
    return app_id, app_secret


def get_user_access_token() -> str:
    token = _get_credential("user_access_token")
    expires_at_str = _get_credential("token_expires_at")

    if token and expires_at_str:
        try:
            expires_at = float(expires_at_str)
            if time.time() < expires_at - 60:
                return token
        except ValueError:
            pass

    refresh_token = _get_credential("refresh_token")
    if not refresh_token:
        output_error("token_expired", "请先执行 login 命令获取用户身份 token")

    return _do_refresh(refresh_token)


def _do_refresh(refresh_token: str) -> str:
    import lark_oapi as lark
    from lark_oapi.api.authen.v1 import (
        CreateRefreshAccessTokenRequest,
        CreateRefreshAccessTokenRequestBody,
    )

    app_id, app_secret = get_app_credentials()
    client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()

    request = (
        CreateRefreshAccessTokenRequest.builder()
        .request_body(
            CreateRefreshAccessTokenRequestBody.builder()
            .grant_type("refresh_token")
            .refresh_token(refresh_token)
            .build()
        )
        .build()
    )
    response = client.authen.v1.refresh_access_token.create(request)

    if not response.success():
        output_error("token_expired", "refresh_token 已过期，请重新执行 login 命令")

    new_token = response.data.access_token
    new_refresh = response.data.refresh_token
    expires_in = response.data.expires_in or 7200

    _set_credential("user_access_token", new_token)
    _set_credential("refresh_token", new_refresh)
    _set_credential("token_expires_at", str(time.time() + expires_in))

    return new_token


def create_client():
    import lark_oapi as lark
    app_id, app_secret = get_app_credentials()
    return lark.Client.builder().app_id(app_id).app_secret(app_secret).build()


def cmd_init() -> None:
    print("配置飞书应用凭证")
    app_id = input("APP_ID: ").strip()
    if not app_id:
        output_error("invalid_input", "APP_ID 不能为空")
    app_secret = getpass.getpass("APP_SECRET (隐藏输入): ").strip()
    if not app_secret:
        output_error("invalid_input", "APP_SECRET 不能为空")

    _set_credential("app_id", app_id)
    _set_credential("app_secret", app_secret)

    try:
        import lark_oapi as lark
        client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
        from lark_oapi.api.wiki.v2 import ListSpaceRequest
        request = ListSpaceRequest.builder().page_size(1).build()
        response = client.wiki.v2.space.list(request)
        if not response.success():
            _delete_credential("app_id")
            _delete_credential("app_secret")
            output_error("auth_failed", f"凭证验证失败: {response.msg}")
    except Exception as e:
        _delete_credential("app_id")
        _delete_credential("app_secret")
        output_error("auth_failed", f"凭证验证失败: {e}")

    output_json({"status": "ok", "message": "配置完成，凭证已保存"})


def cmd_login() -> None:
    """通过 OAuth 登录获取 user_access_token。"""
    import http.server
    import webbrowser
    from urllib.parse import parse_qs, urlparse

    from lark_oapi.api.authen.v1 import (
        CreateAccessTokenRequest,
        CreateAccessTokenRequestBody,
    )

    app_id, app_secret = get_app_credentials()
    port = 3000
    auth_code_holder = {"code": None}

    class CallbackHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            params = parse_qs(urlparse(self.path).query)
            if "code" in params:
                auth_code_holder["code"] = params["code"][0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write("授权成功！可以关闭此页面。".encode())
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"No code received")

        def log_message(self, format, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", port), CallbackHandler)
    server.timeout = 300

    auth_url = (
        f"https://open.feishu.cn/open-apis/authen/v1/authorize"
        f"?app_id={app_id}"
        f"&redirect_uri=http://localhost:{port}/callback"
        f"&scope=wiki:wiki:readonly docx:document:readonly search:docs:read"
        f"&state=cli_login"
    )

    print(f"正在打开浏览器进行飞书授权...", file=sys.stderr)
    print(f"如果浏览器未自动打开，请手动访问:\n{auth_url}\n", file=sys.stderr)
    webbrowser.open(auth_url)

    print("等待授权回调...", file=sys.stderr)
    start = time.time()
    while auth_code_holder["code"] is None:
        if time.time() - start > 300:
            server.server_close()
            output_error("login_timeout", "OAuth 授权超时（5分钟），请重试")
        server.handle_request()
    server.server_close()

    code = auth_code_holder["code"]
    print("收到授权码，正在获取 token...", file=sys.stderr)

    client = create_client()
    request = (
        CreateAccessTokenRequest.builder()
        .request_body(
            CreateAccessTokenRequestBody.builder()
            .grant_type("authorization_code")
            .code(code)
            .build()
        )
        .build()
    )
    response = client.authen.v1.access_token.create(request)

    if not response.success():
        output_error("login_failed", f"获取 token 失败: {response.msg}", response.code)

    access_token = response.data.access_token
    refresh_token = response.data.refresh_token
    expires_in = response.data.expires_in or 7200

    _set_credential("user_access_token", access_token)
    _set_credential("refresh_token", refresh_token)
    _set_credential("token_expires_at", str(time.time() + expires_in))

    output_json({
        "status": "ok",
        "message": f"登录成功！用户: {response.data.name}",
        "name": response.data.name,
        "expires_in": expires_in,
    })


def cmd_refresh() -> None:
    """刷新 user_access_token。"""
    token = get_user_access_token()
    output_json({"status": "ok", "message": "token 有效"})


def cmd_list_spaces() -> None:
    """列出所有知识空间。"""
    from lark_oapi.api.wiki.v2 import ListSpaceRequest

    client = create_client()
    page_token = ""
    all_spaces = []

    while True:
        request = ListSpaceRequest.builder().page_size(50).page_token(page_token).build()
        response = client.wiki.v2.space.list(request)

        if not response.success():
            output_error("api_error", response.msg, response.code)

        if response.data and response.data.items:
            for space in response.data.items:
                all_spaces.append({
                    "space_id": space.space_id,
                    "name": space.name,
                    "description": space.description,
                })

        if not response.data or not response.data.has_more:
            break
        page_token = response.data.page_token

    output_json(all_spaces)


def cmd_list_nodes(space_id: str) -> None:
    """列出指定空间下的一级节点。"""
    from lark_oapi.api.wiki.v2 import ListSpaceNodeRequest

    client = create_client()
    page_token = ""
    all_nodes = []

    while True:
        request = (
            ListSpaceNodeRequest.builder()
            .space_id(space_id)
            .page_size(50)
            .page_token(page_token)
            .build()
        )
        response = client.wiki.v2.space_node.list(request)

        if not response.success():
            output_error("api_error", response.msg, response.code)

        if response.data and response.data.items:
            for node in response.data.items:
                all_nodes.append({
                    "node_token": node.node_token,
                    "obj_token": node.obj_token,
                    "obj_type": node.obj_type,
                    "title": node.title,
                    "has_child": node.has_child,
                })

        if not response.data or not response.data.has_more:
            break
        page_token = response.data.page_token

    output_json(all_nodes)


def cmd_list_child_nodes(space_id: str, parent_node_token: str) -> None:
    """列出指定节点的子节点。"""
    from lark_oapi.api.wiki.v2 import ListSpaceNodeRequest

    client = create_client()
    page_token = ""
    all_nodes = []

    while True:
        request = (
            ListSpaceNodeRequest.builder()
            .space_id(space_id)
            .parent_node_token(parent_node_token)
            .page_size(50)
            .page_token(page_token)
            .build()
        )
        response = client.wiki.v2.space_node.list(request)

        if not response.success():
            output_error("api_error", response.msg, response.code)

        if response.data and response.data.items:
            for node in response.data.items:
                all_nodes.append({
                    "node_token": node.node_token,
                    "obj_token": node.obj_token,
                    "obj_type": node.obj_type,
                    "title": node.title,
                    "has_child": node.has_child,
                })

        if not response.data or not response.data.has_more:
            break
        page_token = response.data.page_token

    output_json(all_nodes)


def cmd_search(query: str, space_id: str | None, node_id: str | None) -> None:
    """搜索知识库文档（HTTP API 直调）。"""
    import requests

    if node_id and not space_id:
        output_error("invalid_args", "传入 --node-id 时必须同时传入 --space-id")

    user_token = get_user_access_token()

    url = "https://open.feishu.cn/open-apis/wiki/v2/nodes/search"
    headers = {
        "Authorization": f"Bearer {user_token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    page_token = ""
    all_results = []

    while True:
        params = {"page_size": 20}
        if page_token:
            params["page_token"] = page_token

        body = {"query": query}
        if space_id:
            body["space_id"] = space_id
        if node_id:
            body["node_id"] = node_id

        resp = requests.post(url, headers=headers, params=params, json=body, timeout=30)
        data = resp.json()

        if data.get("code", 0) != 0:
            output_error("api_error", data.get("msg", "搜索请求失败"), data.get("code"))

        items = data.get("data", {}).get("items", [])
        for item in items:
            all_results.append({
                "node_id": item.get("node_id"),
                "obj_token": item.get("obj_token"),
                "space_id": item.get("space_id"),
                "obj_type": item.get("obj_type"),
                "title": item.get("title"),
                "url": item.get("url"),
            })

        has_more = data.get("data", {}).get("has_more", False)
        if not has_more:
            break
        page_token = data.get("data", {}).get("page_token", "")

    output_json(all_results)


def cmd_get_document(document_id: str) -> None:
    """获取文档正文内容（仅支持 docx 类型）。"""
    from lark_oapi.api.docx.v1 import RawContentDocumentRequest

    client = create_client()
    request = RawContentDocumentRequest.builder().document_id(document_id).build()
    response = client.docx.v1.document.raw_content(request)

    if not response.success():
        output_error("api_error", response.msg, response.code)

    output_json({
        "document_id": document_id,
        "content": response.data.content,
    })


def main():
    parser = argparse.ArgumentParser(description="飞书知识库 Skill 后端")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    # init
    subparsers.add_parser("init", help="配置 APP_ID/APP_SECRET")

    # login
    subparsers.add_parser("login", help="OAuth 登录获取 user_access_token")

    # refresh
    subparsers.add_parser("refresh", help="刷新 user_access_token")

    # list-spaces
    subparsers.add_parser("list-spaces", help="列出所有知识空间")

    # list-nodes
    ln = subparsers.add_parser("list-nodes", help="列出空间下一级节点")
    ln.add_argument("--space-id", required=True, help="知识空间 ID")

    # list-child-nodes
    lcn = subparsers.add_parser("list-child-nodes", help="列出指定节点的子节点")
    lcn.add_argument("--space-id", required=True, help="知识空间 ID")
    lcn.add_argument("--parent-node-token", required=True, help="父节点 token")

    # search
    s = subparsers.add_parser("search", help="搜索知识库文档")
    s.add_argument("--query", required=True, help="搜索关键词")
    s.add_argument("--space-id", help="限定知识空间（可选）")
    s.add_argument("--node-id", help="限定节点及子节点（需同时传 --space-id）")

    # get-document
    gd = subparsers.add_parser("get-document", help="获取文档正文")
    gd.add_argument("--document-id", required=True, help="文档 ID（obj_token）")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "init":
        cmd_init()
    elif args.command == "login":
        cmd_login()
    elif args.command == "refresh":
        cmd_refresh()
    elif args.command == "list-spaces":
        cmd_list_spaces()
    elif args.command == "list-nodes":
        cmd_list_nodes(args.space_id)
    elif args.command == "list-child-nodes":
        cmd_list_child_nodes(args.space_id, args.parent_node_token)
    elif args.command == "search":
        cmd_search(args.query, args.space_id, args.node_id)
    elif args.command == "get-document":
        cmd_get_document(args.document_id)


if __name__ == "__main__":
    main()
