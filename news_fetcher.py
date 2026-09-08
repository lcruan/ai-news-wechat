import urllib.request
import xml.etree.ElementTree as ET

RSS_SOURCES = {
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/technology-lab",
    "MIT Technology Review": "https://www.technologyreview.com/feed/",
}

def fetch_rss(name, url):
    print(f"\n========== {name} ==========")

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0"
            }
        )

        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read()

        root = ET.fromstring(data)

        # RSS
        items = root.findall(".//item")

        # Atom
        if not items:
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

        count = 0

        for item in items:
            title = item.find("title")

            if title is None:
                title = item.find("{http://www.w3.org/2005/Atom}title")

            if title is not None:
                print(f"- {title.text.strip()}")
                count += 1

            if count >= 10:
                break

        print(f"成功获取 {count} 条新闻")

    except Exception as e:
        print(f"抓取失败：{e}")


if __name__ == "__main__":
    print("开始抓取 AI 新闻...")
    
    for name, url in RSS_SOURCES.items():
        fetch_rss(name, url)

    print("\n新闻抓取任务完成！")
