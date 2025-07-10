import os
import csv
import time
import ast
import json
import textwrap
import pandas as pd
from urllib.parse import quote
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import re
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()
openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def extract_majors_from_text(university_name, visible_text):
    system_prompt = (
        "You are a data analyst extracting academic majors from a U.S. university profile page.\n"
        "Your task: identify all majors/programs offered by the university from the visible text.\n"
        "Response format (JSON list):\n"
        "[\n"
        "  {\"label\": \"Major name\"},\n"
        "  ...\n"
        "]"
    )

    chunks = textwrap.wrap(visible_text, width=3000, break_long_words=False, replace_whitespace=False)
    messages = [{"role": "system", "content": system_prompt}]

    for chunk in chunks[:-1]:
        messages.append({"role": "user", "content": f"(Partial chunk from {university_name}):\n{chunk}"})
    messages.append({"role": "user", "content": f"(Final chunk from {university_name}):\n{chunks[-1]}"})

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=messages,
            temperature=0,
            max_tokens=2048,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"[GPT ERROR]: {str(e)}"

def get_visible_major_text(driver):
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    for div in soup.find_all("div"):
        text = div.get_text(separator="\n").strip()
        if "Programs/Majors" in text or "Degree Programs" in text or "Major" in text:
            return text
    raise Exception("Could not find Programs/Majors section")

def click_majors_tab(driver):
    try:
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, "Programs/Majors"))).click()
        print(" Clicked Programs/Majors tab")
        return True
    except:
        print(" Programs/Majors tab not found by direct text, using fallback...")
        for link in driver.find_elements(By.TAG_NAME, "a"):
            link_text = link.text.strip().replace('\xa0', ' ').lower()
            if ("majors" in link_text) or ("programs" in link_text):
                try:
                    driver.execute_script("arguments[0].scrollIntoView(true);", link)
                    time.sleep(0.5)
                    link.click()
                    print(f"Fallback clicked: {link.text}")
                    return True
                except:
                    continue
    return False

def extract_json_list(raw):
    cleaned = re.sub(r"```(json)?", "", raw).strip()
    match = re.search(r"\[.*?\]", cleaned, re.DOTALL)
    if match:
        json_str = match.group(0)
        try:
            return json.loads(json_str)
        except:
            try:
                return ast.literal_eval(json_str)
            except:
                pass
    raise ValueError("No JSON list found in GPT output")

def process_university(university_name, retries=2):
    for attempt in range(retries):
        url = f"https://nces.ed.gov/collegenavigator/?q={quote(university_name)}"
        options = Options()
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        driver = webdriver.Chrome(options=options)
        try:
            driver.get(url)
            time.sleep(1)

            
            if "No matching institutions found" in driver.page_source:
                print(f"University not found: {university_name}")
                return [{"university": university_name, "major": "", "error": "UNIVERSITY NOT FOUND"}]

            
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".resultsTable a"))).click()
            print(f" Clicked university: {university_name}")

            if not click_majors_tab(driver):
                raise Exception("Programs/Majors tab not found")

            visible_text = get_visible_major_text(driver)
            raw = extract_majors_from_text(university_name, visible_text)
            print("Raw GPT output:\n", raw)

            if raw.startswith("[GPT ERROR]"):
                return [{"university": university_name, "major": "", "error": raw}]

            try:
                records = extract_json_list(raw)
            except Exception as e:
                return [{"university": university_name, "major": "", "error": f"PARSE ERROR: {e}"}]

            results = []
            for rec in records:
                label = rec.get("label", "")
                results.append({"university": university_name, "major": label, "error": ""})

            return results

        except Exception as e:
            print(f"Attempt {attempt+1} failed for {university_name}: {e}")
            time.sleep(2)
        finally:
            driver.quit()
    return [{"university": university_name, "major": "", "error": f"TOTAL ERROR after {retries} retries"}]


def scrape_all(input_csv, output_csv):
    df = pd.read_csv(input_csv)
    fieldnames = ["university", "major", "error"]

    with open(output_csv, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if f.tell() == 0:
            writer.writeheader()

        for i, row in df.iterrows():
            university = row["university"]
            print(f"\n [{i+1}/{len(df)}] Scraping: {university}")
            results = process_university(university)
            for result in results:
                writer.writerow(result)
            f.flush()
            time.sleep(2)

    print(f"\n Done. Data saved to {output_csv}")

if __name__ == "__main__":
    scrape_all("us_universities.csv", "latest_majors.csv")
