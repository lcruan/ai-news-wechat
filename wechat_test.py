import os
import json
import urllib.request
import urllib.error


WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID")
WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET")

WECHAT_TOKEN_URL = "https://api.weixin.qq.com/cgi-bin/token"


def get_access_token():
    if not WECHAT_APP_ID:
        raise RuntimeError(
            "没有找到 WECHAT_APP_ID，请检查 GitHub Secrets。"
        )

    if not WECHAT_APP_SECRET:
        raise RuntimeError(
            "没有找到 WECHAT_APP_SECRET，请检查 GitHub Secrets。"
        )

    url = (
        f"{WECHAT_TOKEN_URL}"
        f"?grant_type=client_credential"
        f"&appid={WECHAT_APP_ID}"
        f"&secret={WECHAT_APP_SECRET}"
    )

    print("正在请求微信公众号 access_token...")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AI-News-WeChat-Automation/1.0"
        },
        method="GET"
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:

            response_data = response.read()

        result = json.loads(
            response_data.decode("utf-8")
        )

    except Exception as e:
        raise RuntimeError(
            f"请求微信公众号接口失败：{e}"
        )

    if "access_token" not in result:
        errcode = result.get("errcode")
        errmsg = result.get("errmsg")

        raise RuntimeError(
            f"微信公众号返回错误："
            f"errcode={errcode}, errmsg={errmsg}"
        )

    access_token = result["access_token"]

    if not access_token:
        raise RuntimeError(
            "微信公众号返回的 access_token 为空。"
        )

    print("========================================")
    print("微信公众号 API 连接成功！")
    print("AppID 已成功读取")
    print("AppSecret 已成功读取")
    print("access_token 已成功获取")
    print("========================================")


if __name__ == "__main__":
    get_access_token()
