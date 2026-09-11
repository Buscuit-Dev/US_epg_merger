import asyncio
import re
import xml.etree.ElementTree as ET
import aiohttp
from playwright.sync_api import sync_playwright

TARGET_URL = "https://epg.pw/areas/us.html?lang=en&timezone=VVMvQ2VudHJhbA%3D%3D"
OUTPUT_FILE = "master_epg.xml"
CONCURRENCY_LIMIT = 500

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

def extract_channel_ids():
    print("Launching browser to extract channel IDs...")
    channel_ids = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(user_agent=HEADERS['User-Agent'])

        print("Loading main US listing...")
        page.goto(TARGET_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_selector("table", timeout=20000)
        page.wait_for_timeout(3000)

        html_content = page.content()
        ids = re.findall(r'/last/(\d+)\.html', html_content)
        for cid in ids:
            channel_ids.add(cid)

        if not channel_ids:
            hrefs = page.eval_on_selector_all("a", "elements => elements.map(e => e.getAttribute('href'))")
            for h in hrefs:
                if h and '/last/' in h:
                    m = re.search(r'/last/(\d+)\.html', h)
                    if m:
                        channel_ids.add(m.group(1))

        browser.close()

    print(f"Extracted {len(channel_ids)} unique channel IDs.")
    return sorted(list(channel_ids))

def parse_xml_payload(content):
    try:
        return ET.fromstring(content)
    except Exception:
        return None

async def fetch_and_parse_api_xml(session, semaphore, cid, root_tv, seen_channels, progress):
    url = f"https://epg.pw/api/epg.xml?channel_id={cid}"
    async with semaphore:
        try:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    content = await response.read()
                    tree = await asyncio.to_thread(parse_xml_payload, content)
                    
                    if tree is not None:
                        has_elements = False
                        for elem in tree:
                            if elem.tag == 'channel':
                                raw_id = elem.get('id') or ''
                                unique_id = f"epg_{cid}_{raw_id}" if raw_id else f"epg_{cid}"
                                
                                if unique_id in seen_channels:
                                    continue
                                seen_channels.add(unique_id)
                                elem.set('id', unique_id)
                                root_tv.append(elem)
                                has_elements = True
                            elif elem.tag == 'programme':
                                raw_id = elem.get('channel') or ''
                                unique_id = f"epg_{cid}_{raw_id}" if raw_id else f"epg_{cid}"
                                elem.set('channel', unique_id)
                                root_tv.append(elem)
                                has_elements = True

                        if has_elements:
                            progress['success'] += 1
        except Exception:
            pass
        finally:
            progress['count'] += 1
            if progress['count'] % 500 == 0 or progress['count'] == progress['total']:
                print(f"Processed [{progress['count']}/{progress['total']}] API feeds ({len(seen_channels)} unique channels merged)...")

async def build_master_epg_async(channel_ids):
    if not channel_ids:
        print("No channel IDs found to process. Exiting.")
        return

    root_tv = ET.Element("tv", {"generator-info-name": "Merged-EPG-Pw"})
    seen_channels = set()
    semaphore = asyncio.Semaphore(CONCURRENCY_LIMIT)
    progress = {'count': 0, 'success': 0, 'total': len(channel_ids)}

    connector = aiohttp.TCPConnector(limit=CONCURRENCY_LIMIT, limit_per_host=CONCURRENCY_LIMIT)

    print(f"\nFetching and merging {len(channel_ids)} API feeds ({CONCURRENCY_LIMIT} concurrent workers)...")
    async with aiohttp.ClientSession(headers=HEADERS, connector=connector) as session:
        tasks = [
            fetch_and_parse_api_xml(session, semaphore, cid, root_tv, seen_channels, progress)
            for cid in channel_ids
        ]
        await asyncio.gather(*tasks)

    print("\nWriting master XML file to disk...")
    tree = ET.ElementTree(root_tv)
    
    # Explicitly opening the file handle prevents the macOS Python 3.9 'Bad file descriptor' OSError
    with open(OUTPUT_FILE, "wb") as f:
        tree.write(f, encoding="utf-8", xml_declaration=True)
        
    print(f"Done! Master EPG successfully written to '{OUTPUT_FILE}' with {len(seen_channels)} total channels.")

if __name__ == "__main__":
    cids = extract_channel_ids()
    asyncio.run(build_master_epg_async(cids))
