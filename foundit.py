from playwright.sync_api import sync_playwright
import csv
import time
import random
import json
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import os

SEARCH_URL_TEMP = "https://www.foundit.in/search/frontend-developer-jobs?start=1&limit=30&query={}&queryDerived=true"
DOMAINS = [
    ("Frontend Development", "Frontend+Developer"),
    ("Software Engineer", "Software+Engineer"),
    ("Data Aanlyst", "Data+Analyst"),
    ("Data Engineer", "Data+Engineer"),
    ("Cyber Security", "Cyber+Security"),
    ("Artificial Intelligence", "Artificial+Intelligence"),
    ("Machine Learning", "Machine+Learning")
]
# ("Frontend Development", "frontend-development"),
#     ("Software Engineer", "software-engineering"), 
#     ("Data Analyst", "data-analyst"),
#     ("Data Engineer", "data-engineer"),
#     ("Cyber Security", "cyber-security")

STATE_FILE = "foundit_state.json"
OUTPUT_CSV = "foundit_job.csv"
MAX_PAGES = 3

def human_wait(min_s=1.0, max_s=3.0):
    time.sleep(random.uniform(min_s, max_s))

def get_page_url(base_url, page_number, domain_name, limit=30):

    
    parsed = urlparse(base_url)
    query_parms = parse_qs(parsed.query)

    job_slug = domain_name.lower().replace(' ', '-')
    query_parms['query'] = [job_slug]

    start_value = page_number
    query_parms['start'] = [str(start_value)]

    new_query = urlencode(query_parms, doseq=True)
    new_url = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        parsed.fragment
    ))

    return new_url

def get_total_job_count(page):
    try:
        no_of_jobs = page.query_selector_all("div[data-index].flex.w-full.flex-col")

        if no_of_jobs:
            total_job_on_page = len(no_of_jobs)
            return int(total_job_on_page)
        else:
            print("No jobs were found")
            return None
    except:
        return None

def extract_job_info(new_tab, job_link):

    try:
        new_tab.wait_for_selector("div#jobDescription", timeout=20000)
        print("DEBUG: jobDescription loaded")
    except Exception as e:
        print("❌ Job page content did not load:", e)
        return {}
    
    human_wait(1,2)
    job_info = {}

    job_info["job_link"] = job_link
    
    try:
        job_title_class = new_tab.query_selector("#jdPageHeader h1")
        if job_title_class:
            job_title = job_title_class.text_content()
        else:
            job_title = ""
        job_info["job_title"] = job_title
    
    except Exception as e:
        print("ERROR in job_title extraction:", e)
        job_info["job_title"] = ""

    try:
        company_name_class = new_tab.query_selector("div.text-content-primary-inverse a")

        if company_name_class:
            company_name = company_name_class.text_content().strip()
            company_link = company_name_class.get_attribute("href")
            if company_link and company_link.startswith("/"):
                company_link = "https://www.foundit.in" + company_link
        else:
            company_name = ""
            company_link = ""
        
        job_info['company_name'] = company_name
        job_info['company_link'] = company_link
    except:
        print("ERROR in company name:", e)
        job_info['company_name'] = ""
        job_info['company_link'] = ""


    try:
        posted_day_class = new_tab.query_selector("div.text-content-tertiary ul.flex.gap-4 span")
        if posted_day_class:
            posted_day = posted_day_class.text_content().strip()
        else:
            posted_day = ""

        job_info["posted_info"] = posted_day
    except:
        print("ERROR in posted info:", e)
        job_info["posted_info"] = ""

    try:
        applicant_classs = new_tab.query_selector_all("div.text-content-tertiary span")
        if applicant_classs:
            applicant = applicant_classs[1].text_content().strip()
        else:
            applicant = ""
        
        job_info['applicant'] = applicant
    except:
        print("ERROR in applicant", e)
        job_info['applicant'] = ""

    try:
        # Method 1: Try the exact selector first
        logo_class = new_tab.query_selector("#jdPageHeader img[src*='jdlogo.gif']")
        
        if logo_class:
            logo = logo_class.get_attribute("src")
        else:
            logo = ""
        
        job_info["logo_link"] = logo

    except Exception as e:
        print(f"Error extracting logo: {e}")
        job_info["logo_link"] = ""

    try:
        location_class = new_tab.query_selector_all("#jdPageHeader a[href*='jobs-in']")

        locations = []

        for el in location_class:
            text = el.text_content().strip()
            locations.append(text)

        job_info['location'] = ", ".join(locations)
    except:
        job_info['location'] = ""

    try:
        experience = ""

        spans = new_tab.query_selector_all("#jdPageHeader span")

        for span in spans:
            text = span.text_content().strip()
            if "year" in text.lower():
                experience = text
                break

        job_info["experience"] = experience
    
    except:
        job_info["experience"] = ""


    # try:
    #     container = new_tab.query_selector_all("div.text-content-primary.flex.gap-4")
    #     experience = ""
    #     salary = ""
    #     loc = ""
        
    #     if len(container) >= 2:
    #         exp_sal_container = container[0]
    #         location_container = container[1]

    #         sal_info_block = exp_sal_container.query_selector_all("div.flex.items-center.gap-2")
            
    #         # Fix: Access the first element when length is 1
    #         if len(sal_info_block) == 1:
    #             experience = sal_info_block[0].text_content().strip()
    #             salary = ""
    #         elif len(sal_info_block) >= 2:
    #             experience = sal_info_block[0].text_content().strip()
    #             salary = sal_info_block[1].text_content().strip()

    #         loc_info_block = location_container.query_selector_all("div.flex.items-center.gap-2 a")
    #         loc_list = []
    #         for l in loc_info_block:
    #             loc_str = l.text_content().strip()
    #             if loc_str:
    #                 loc_list.append(loc_str)
    #         loc = ", ".join(loc_list)
        
    #     job_info["experience"] = experience
    #     job_info["salary"] = salary
    #     job_info["location"] = loc

    #     print(f"✓ Experience: {experience if experience else 'Not found'}")
    #     print(f"✓ Salary: {salary if salary else 'Not found'}")
    #     print(f"✓ Location: {loc if loc else 'Not found'}")

    # except Exception as e:
    #     print(f"✗ Error extracting exp/sal/loc: {e}")
    #     job_info["experience"] = ""
    #     job_info["salary"] = ""
    #     job_info["location"] = ""

    try:
        apply_class = new_tab.query_selector("div.ml-6.mt-6.w-max a")
        if apply_class:
            apply = apply_class.get_attribute("href")
            if apply and apply.startswith("/"):
                apply = "https://www.foundit.in" + apply
        else:
            apply = ""
        
        job_info["apply_link"] = apply
    
    except:
        job_info["apply_link"] = ""

    try:
        jd_class = new_tab.query_selector("div#jobDescription")
        if jd_class:
            jd = jd_class.text_content().strip()
        else:
            jd = ""
        job_info["jd"] = jd
    except Exception as e:
        print(f"Error extracting job description: {e}")
        job_info["jd"] = ""

    try:
        info_rows = new_tab.query_selector_all("div.flex.text-sm")

        job_info["job_working_des"] = ""
        job_info["industry_type"] = ""
        job_info["job_type"] = ""

        for row in info_rows:
            label_el = row.query_selector("div.text-content-primary")
            value_el = row.query_selector("div.text-content-secondary")

            if not label_el or not value_el:
                continue

            label = label_el.text_content().strip().lower().replace(":", "")
            value = value_el.text_content().strip()

            if label == "job type":
                job_info["job_working_des"] = value

            elif label == "industry":
                job_info["industry_type"] = value

            elif label == "employment type":
                job_info["job_type"] = value

    except Exception as e:
        print(f"❌ Error extracting job stats: {e}")

    # try:
    #     industry_element = new_tab.query_selector("p.flex.gap-1:has(span:text('Industry:')) a")
    #     if industry_element:
    #         industry = industry_element.text_content().strip()
    #     else:
    #         industry = ""
    #     job_info["industry"] = industry
    # except:
    #     job_info["industry"] = ""

    # try:
    #     role_element = new_tab.query_selector("p.flex.gap-1:has(span:text('Role:')) a")
    #     if role_element:
    #         job_role = role_element.text_content().strip()
    #     else:
    #         job_role = ""

    #     job_info["job_role"] = job_role 
    
    # except:
    #     job_info["job_role"] = ""

    # try:
    #     job_type_element = new_tab.query_selector("p.flex.gap-1:has(span:text('Job Type:')) a")
    #     if job_type_element:
    #         job_type = job_type_element.text_content().strip()
    #     else:
    #         job_type = ""
    #     job_info["job_type"] = job_type
    
    # except:
    #     job_info["job_type"] = ""

    # try:
    #     job_working_des_element = new_tab.query_selector()
    
    try:
        skill_class = new_tab.query_selector_all("div.flex.flex-wrap a")
        if skill_class:
            skill_list = []
            for s in skill_class:
                skill_str = s.text_content()
                skill_list.append(skill_str)
            skill = ",".join(skill_list)
        else:
            skill = ""

        job_info["skill"] = skill
    except:
        job_info["skill"] = ""

    return job_info


def click_job_link(context,page, card_index):
    try:

        job_cards = page.query_selector_all("div[data-index].flex.w-full.flex-col")

        if card_index < len(job_cards):
            card = job_cards[card_index]
            link_element = card.query_selector("h2 a")

            if link_element:
                job_new_tab_url = link_element.get_attribute("href")
                
                if job_new_tab_url:
                    with context.expect_page() as new_page_info:
                        link_element.click()
                    
                    new_page = new_page_info.value
                    new_page.wait_for_load_state("domcontentloaded")
                    # new_page.wait_for_selector("h1", timeout=15000)

                    job_data = extract_job_info(new_page,job_new_tab_url)

                    new_page.close()
                    return job_data
                
        return False
    except Exception as e:
        print(f"   ❌ Error clicking job card {card_index}: {e}")
        return False


def process_single_page(context,page, page_num, all_rows, domain_name):
    """Process all jobs on a single page"""
    print(f"\n🔍 Processing Page {page_num}...")

    human_wait(1,2)

    # jobs_on_page = scroll_page(page, pause =2, max_scroll= 15)

    # if jobs_on_page == 0:
    #     print(f"   ⚠️ No jobs loaded on page {page_num}")
    #     return 0

    # total_job_count_single_page = get_total_job_count(page)

    # if jobs_on_page == total_job_count_single_page:
    #     print("Matching")
    # else:
    #     print(f"Found difference in {jobs_on_page} : {total_job_count_single_page}")

    # print(f"Found {jobs_on_page} job cards on page {page_num}")

    cards = page.query_selector_all("div[data-index].flex.w-full.flex-col")

    page_jobs_processed = 0

    for i , card in enumerate(cards):
        job_number = len(all_rows) + 1
        print(f"\n   📋 Processing job {job_number} (Page {page_num}, Card {i+1}/{len(cards)})...")

        job_data = click_job_link(context, page, i)

        if job_data:
            job_data["domain"] = domain_name
            job_data["scrapped_at"] = time.strftime("%Y:%m:%d")

            all_rows.append(job_data)

            page_jobs_processed += 1
            print("      📊 ✅ Job data extracted successfully")
        else:
            print(f"      ❌ Failed to extract job {i+1}")
        
    print(f"   ✅ Page {page_num} complete: {page_jobs_processed}/{len(cards)} jobs processed")
    return page_jobs_processed

def check_pagination_available(page):
    try:
        # Look for the "Next" button with the specific text and SVG
        next_button = page.query_selector("button.inline-flex:has-text('Next')")
        
        if next_button:
            # Check if button is enabled (not disabled)
            is_disabled = next_button.get_attribute("disabled")
            if is_disabled is None:
                return True
        
        return False
        
    except Exception as e:
        print(f"⚠️ Error checking pagination: {e}")
        return False


def main():
    
    OUTPUT_DIRECTORY = r"C:\Users\gis28\.webscrap\dags\output"

    os.makedirs(OUTPUT_DIRECTORY, exist_ok=True)

    state_file_path = os.path.join(OUTPUT_DIRECTORY, STATE_FILE)
    output_csv_path = os.path.join(OUTPUT_DIRECTORY, OUTPUT_CSV)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=[
        '--disable-blink-features=AutomationControlled',
        '--disable-dev-shm-usage',
        '--no-sandbox',
        '--disable-setuid-sandbox',
        '--disable-web-security',
        '--disable-features=VizDisplayCompositor'
        ]
    )
        if os.path.exists(state_file_path):
            print("✅ Found saved login state, loading...")
            context = browser.new_context(storage_state= state_file_path)
            page = context.new_page()
        
        else:
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.foundit.in/rio/sign-out")
            input("🔑 Please log in manually, then press Enter here...")
            context.storage_state(path=state_file_path)
        
        all_rows = []
        for domain_name, url_key in DOMAINS:
            print(f"Scraping {domain_name}...")

            SEARCH_URL = SEARCH_URL_TEMP.format(url_key)

            current_page = 1

            while current_page <= MAX_PAGES:
                page_url = get_page_url(SEARCH_URL, current_page, domain_name)

                try:
                    page.goto(page_url, timeout=60000, wait_until="domcontentloaded")
                
                except Exception as e:
                    print(f"   ❌ Navigation to page {current_page} failed: {e}")
                    break

                # try:
                #     page.wait_for_selector("div.job_seen_beacon, div.jobsearch-NoResult-messageContainer", timeout=15000)

                #     no_results = page.query_selector("div.jobsearch-NoResult-messageContainer.css-sx1muy.eu4oa1w0")
                #     if no_results:
                #         print(f"   ℹ️ No more jobs available (reached end at page {current_page})")
                #         break
                # except:
                #     print(f"   ⚠️ Page {current_page} failed to load properly")
                #     break

                jobs_processed = process_single_page(context, page, current_page, all_rows, domain_name)
                if jobs_processed == 0:
                    print(f"   ⚠️ No jobs processed on page {current_page}, stopping...")
                    break

                if current_page < MAX_PAGES:
                    has_more_pages = check_pagination_available(page)
                    if not has_more_pages:
                        print(f"   ℹ️ No more pages available after page {current_page}")
                        break
                
                current_page += 1
                human_wait(1,2)
        if all_rows:
            fieldnames = ["job_title", "job_link", "logo_link", "company_name", "company_link",
                          "posted_info", "applicant" ,"location", "experience", "skill", 
                          "apply_link", "jd", "job_working_des", "industry_type", "job_type", 
                          "scrapped_at", "domain"
            ]
            with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            
            print(f"\n🎉 Scraping completed!")
            print(f"   📊 Total jobs scraped: {len(all_rows)}")
            print(f"   📄 Pages processed: {current_page - 1}")
            print(f"   💾 Data saved to: {OUTPUT_CSV}")
        else:
            print("\n⚠️ No jobs were scraped!")

        context.close()
        browser.close()

if __name__ == "__main__":
    main()