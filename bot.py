import time, json, re, requests
from html import unescape, escape
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime
from datetime import datetime

# ── 설정 ──────────────────────────────────────────
SEEN_FILE           = "seen.json"
POLL_INTERVAL_SEC   = 10
# ─────────────────────────────────────────────────

def load_seen_links():
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_seen_links(seen):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False, indent=2)

def clean_title(raw):
    text = re.sub(r"<.*?>", "", raw)
    return unescape(text)

def fetch_full_title_from_page(url):
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        og = soup.find('meta', property='og:title')
        if og and og.get('content'):
            return og['content'].strip()
        if soup.title and soup.title.string:
            return soup.title.string.strip()
    except Exception:
        pass
    return None

def fetch_press_from_page(url):
    """
    기사 페이지의 og:site_name 또는 og:article:author 메타에서 언론사명 추출
    """
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        # og:site_name 메타
        site = soup.find('meta', property='og:site_name')
        if site and site.get('content'):
            return site['content'].strip()
        # og:article:author 메타
        author = soup.find('meta', property='og:article:author')
        if author and author.get('content'):
            return author['content'].strip()
    except Exception:
        pass
    # fallback: 도메인에서 추출
    m = re.search(r"https?://(?:www\.)?([^/.]+)", url)
    if m:
        return m.group(1)
    return "언론사 미상"

def fetch_time_from_page(url):
    """
    기사 페이지의 og:article:published_time 메타에서 실제 게시 시간 추출
    """
    try:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'html.parser')
        meta = soup.find('meta', property='article:published_time')
        if meta and meta.get('content'):
            dt = parsedate_to_datetime(meta['content'])
            return dt
    except Exception:
        pass
    return None

def fetch_naver_news(query, display=10):
    url = "https://openapi.naver.com/v1/search/news.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
    }
    params = {"query": query, "sort": "date", "display": display}
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json().get("items", [])

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    resp = requests.post(url, data=payload)
    if resp.status_code != 200:
        print("Telegram API Error:", resp.status_code, resp.text)
        resp.raise_for_status()

def main():
    seen = load_seen_links()
    items = fetch_naver_news(QUERY, display=50)  # 상위 50건 조회

    for it in reversed(items):
        link = it.get("originallink") or it.get("link")
        raw_title = it.get("title", "")
        title = clean_title(raw_title)

        # API pubDate 파싱
        try:
            pub_dt = parsedate_to_datetime(it.get("pubDate", ""))
        except:
            pub_dt = None

        # 페이지에서 실제 게시 시간 시도
        page_dt = fetch_time_from_page(link) if pub_dt else None
        final_dt = page_dt or pub_dt
        time_str = final_dt.strftime("%Y-%m-%d %H:%M") if final_dt else "시간 미상"

        # 페이지에서 언론사명 추출
        press = fetch_press_from_page(link)

        # 제목이 생략된 경우 전체 제목 시도
        if title.endswith('...') or title.endswith('…'):
            full = fetch_full_title_from_page(link)
            if full:
                title = full

        if link not in seen:
            safe_title = escape(title)
            safe_press = escape(press)
            msg = f'<a href="{link}">{safe_title}</a>\n{safe_press} / {time_str}'
            try:
                send_telegram_message(msg)
                seen.add(link)
            except Exception as e:
                print("Failed sending:", link, e)

    save_seen_links(seen)

if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:
            print("Error in main loop:", e)
        time.sleep(POLL_INTERVAL_SEC)
