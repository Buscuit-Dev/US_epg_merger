import re
import urllib.request
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup

# URL containing the full listing you want to target
TARGET_AREA_URL = "https://epg.pw/areas/us.html"
OUTPUT_FILE = "master_epg.xml"

def get_channel_pages(area_url):
    print("Fetching channel list...")
    req = urllib.request.Request(area_url, headers={'User-Agent': 'Mozilla/5.0'})
    html = urllib.request.urlopen(req).read().decode('utf-8')
    soup = BeautifulSoup(html, 'html.parser')
    
    channel_links = set()
    for a in soup.find_all('a', href=True):
        if '/channel/' in a['href']:
            href = a['href']
            full_url = "https://epg.pw" + href if href.startswith('/') else href
            channel_links.add(full_url)
            
    print(f"Found {len(channel_links)} total channel pages.")
    return channel_links

def extract_xml_urls(channel_pages):
    xml_urls = set()
    for idx, page in enumerate(channel_pages, start=1):
        try:
            print(f"[{idx}/{len(channel_pages)}] Extracting XML from: {page}")
            req = urllib.request.Request(page, headers={'User-Agent': 'Mozilla/5.0'})
            html = urllib.request.urlopen(req).read().decode('utf-8')
            
            # Find all direct .xml links on the page
            matches = re.findall(r'https?://[^\s"]+\.xml', html)
            for m in matches:
                xml_urls.add(m)
        except Exception as e:
            print(f"Failed to load {page}: {e}")
            
    return xml_urls

def build_combined_xml(xml_urls):
    root_tv = ET.Element("tv", {"generator-info-name": "Merged-EPG-Pw"})
    seen_channels = set()
    
    print(f"\nMerging {len(xml_urls)} unique XML files into master file...")
    for url in xml_urls:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            xml_data = urllib.request.urlopen(req).read()
            tree = ET.fromstring(xml_data)
            
            for elem in tree:
                # Deduplicate channels by ID so Dispatcher doesn't break
                if elem.tag == 'channel':
                    channel_id = elem.get('id')
                    if channel_id in seen_channels:
                        continue
                    seen_channels.add(channel_id)
                
                root_tv.append(elem)
        except Exception as e:
            print(f"Error parsing XML at {url}: {e}")
            
    tree = ET.ElementTree(root_tv)
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"\nDone! Master EPG saved as '{OUTPUT_FILE}'.")

if __name__ == "__main__":
    pages = get_channel_pages(TARGET_AREA_URL)
    xml_list = extract_xml_urls(pages)
    build_combined_xml(xml_list)
