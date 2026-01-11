from playwright.sync_api import sync_playwright
import csv
import time
import random
import json
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import os


SEARCH_URL_TEMP = "https://www.linkedin.com/jobs/search/?keywords={}&origin=JOB_SEARCH_PAGE_JOB_FILTER&refresh=true"
DOMAINS = [
    ("Frontend Development", "frontend%20development"),
    ("Software Engineer", "software%20engineer"),
    ("Data Analyst", "data%20analyst"),
    ("Data Engineer", "data%20engineer"),
    ("Cyber Security", "cyber%20security")
]

STATE_FILE = "linkedin_state.json"
# if os.path.exists(STATE_FILE):
#     os.remove(STATE_FILE)freezy2004.27@gmail.com
#     print(f"🗑️ Deleted old state file: {STATE_FILE}")
OUTPUT_CSV = "linkedin_jobs2.csv"
MAX_PAGES = 1

def human_wait(min_s=1.0, max_s=3.0):
    time.sleep(random.uniform(min_s, max_s))

def click_job_card(page, card_index):
    """Click on a specific job card to load its details"""
    try:
        # Find the job card link and click it
        job_cards = page.query_selector_all("li.scaffold-layout__list-item div.job-card-container")
        if card_index < len(job_cards):
            card = job_cards[card_index]
            job_link = card.query_selector("div.artdeco-entity-lockup__title a.job-card-container__link")
            if job_link:
                job_link.click()
                return True
        return False
    except Exception as e:
        print(f"   ❌ Error clicking job card {card_index}: {e}")
        return False
    
def get_page_url(base_url, page_number):
    """Generate URL for specific page number (LinkedIn uses 'start' parameter)"""
    parsed = urlparse(base_url)
    query_params = parse_qs(parsed.query)
    
    # LinkedIn uses 'start' parameter where start = (page_number - 1) * 25
    # Page 1: start=0, Page 2: start=25, Page 3: start=50, etc.
    start_value = (page_number - 1) * 25
    query_params['start'] = [str(start_value)]
    
    # Remove currentJobId to avoid issues with pagination
    if 'currentJobId' in query_params:
        del query_params['currentJobId']
    
    new_query = urlencode(query_params, doseq=True)
    new_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    
    return new_url

def scroll_page(page, pause=1.5, max_scroll=15):
    # ✅ Use locator for the job list container
    job_list = page.locator("div.scaffold-layout__list")

    prev_count = 0
    no_change_count = 0
    
    print("Starting optimized scroll to load all job cards...")
    
    for i in range(max_scroll):
        # Count current jobs
        cards = page.locator("li.scaffold-layout__list-item div.job-card-container")
        current_count = cards.count()
        
        print(f"[{i+1}] Current jobs: {current_count}", end="")
        
        # Smart scrolling strategy based on current state
        if current_count == 0:
            # Initial load - just scroll a bit
            job_list.evaluate("el => el.scrollBy(0, 600)")
        elif no_change_count == 0:
            # Normal scrolling - try to scroll to trigger more loading
            try:
                # Scroll to 2nd-to-last job to trigger loading
                if current_count > 2:
                    target_index = current_count - 2
                    target_card = job_list.locator("li.scaffold-layout__list-item").nth(target_index)
                    target_card.scroll_into_view_if_needed()
                else:
                    job_list.evaluate("el => el.scrollBy(0, 800)")
            except:
                job_list.evaluate("el => el.scrollBy(0, 800)")
        else:
            # Aggressive mode - scroll to last card immediately
            try:
                last_card = job_list.locator("li.scaffold-layout__list-item").last
                last_card.scroll_into_view_if_needed()
            except:
                job_list.evaluate("el => el.scrollTop = el.scrollHeight")
        
        # Wait for content to load (shorter wait)
        time.sleep(pause)
        
        # Count jobs after scrolling
        cards = page.locator("li.scaffold-layout__list-item div.job-card-container")
        count = cards.count()
        change = count - current_count
        
        print(f" → {count} (+{change})")

        # Update counters
        if count > prev_count:
            no_change_count = 0
            prev_count = count
        else:
            no_change_count += 1
            
        # Quick exit if no changes for 2 attempts
        if no_change_count >= 2:
            # One final aggressive attempt
            print("   🚀 Final attempt - scrolling to absolute bottom...")
            try:
                job_list.evaluate("el => el.scrollTop = el.scrollHeight")
                time.sleep(pause * 1.5)  # Slightly longer wait for final attempt
                
                final_cards = page.locator("li.scaffold-layout__list-item div.job-card-container")
                final_count = final_cards.count()
                
                if final_count > count:
                    print(f"   ✨ Final scroll loaded {final_count - count} more jobs!")
                    prev_count = final_count
                else:
                    print(f"✅ Scrolling complete. Total jobs: {prev_count}")
                    break
            except:
                print(f"✅ Scrolling complete. Total jobs: {prev_count}")
                break

    return prev_count

def check_pagination_available(page):
    """Check if there are more pages available"""
    try:
        # Method 1: Check for "Next" button
        next_button = page.query_selector("button[aria-label='View next page']")
        if next_button and not next_button.is_disabled():
            return True
        
        # Method 2: Check pagination numbers
        pagination = page.query_selector("div.artdeco-pagination")
        if pagination:
            # Look for page numbers higher than current
            page_buttons = pagination.query_selector_all("button[aria-label*='Page']")
            if len(page_buttons) > 1:  # More than just current page
                return True
        
        # Method 3: Check if we have reached the end by looking at results
        no_results = page.query_selector("div.jobs-search-no-results-banner")
        if no_results:
            return False
            
        return False
    except Exception as e:
        print(f"   ⚠️ Error checking pagination: {e}")
        return False

def get_total_job_count(page):
    """Extract total number of jobs from the search results header"""
    try:
        # LinkedIn shows "X jobs" or "X,XXX jobs" in the header
        results_text = page.query_selector("div.jobs-search-results-list__title-heading")
        if results_text:
            text = results_text.text_content().strip()
            # Extract number from text like "1,234 Frontend Developer jobs"
            match = re.search(r'([\d,]+)', text)
            if match:
                count_str = match.group(1).replace(',', '')
                return int(count_str)
        return None
    except:
        return None

def extract_job_info(page):
    human_wait(2,4)
    job_info = {}

    try:
        page.wait_for_selector("div.jobs-search__job-details--container", timeout=10000)
        human_wait(1, 2)
    except:
        print("   ❌ Job details panel not loaded")
        return job_info
    try:
        company_name_class = page.query_selector("div.job-details-jobs-unified-top-card__company-name a")
        if company_name_class:
            company_name = company_name_class.text_content().strip()
            company_page_link = company_name_class.get_attribute("href")
        else:
            company_name = ""
            company_page_link = ""
        
        job_info["company_name"] = company_name
        job_info["company_page_link"] = company_page_link
    except:
        job_info["company_name"] = ""
        job_info["company_page_link"] = ""
    
    try:
        company_logo_class = page.query_selector("div.ivm-view-attr__img-wrapper img")
        if company_logo_class:
            company_logo = company_logo_class.get_attribute("src")
        else:
            company_logo = ""
        job_info["company_logo"] = company_logo
    except:
        job_info["company_logo"] = ""
    
    try:
        job_title_class = page.query_selector("div.job-details-jobs-unified-top-card__job-title a")
        if job_title_class:
            job_title = job_title_class.text_content().strip()
            job_link = job_title_class.get_attribute("href")
            if job_link and job_link.startswith("/"):
                job_link = "https://www.linkedin.com" + job_link
        else:
            job_title = ""
            job_link = ""
        
        job_info["job_title"] = job_title
        job_info["job_link"] = job_link
    except:
        job_info["job_title"] = ""
        job_info["job_link"] = ""
    
    try:
        container = page.query_selector("div.job-details-jobs-unified-top-card__primary-description-container")
        
        job_info["job_location"] = ""
        job_info["posted_date"] = ""
        job_info["applicants"] = ""
        job_info["job_priority"] = "Low"
        job_info["application_status"] = ""

        if container:
            spans = container.query_selector_all("span.tvm__text")
            
            if len(spans) == 0:
                raw_text = container.text_content().strip()
            
            for i, span in enumerate(spans, 1):
                text = span.text_content().strip()
                
                # Skip empty or separator text
                if not text or text == "·":
                    print(f"[{i}] Skipped: '{text}' (separator or empty)")
                    continue
                low = text.lower()
                
                # Applicants (check first as it's most specific)
                if not job_info["applicants"] and ("applicant" in low or "clicked apply" in low):
                    # Remove "Promoted" if in same text
                    if "promoted" in low:
                        job_info["applicants"] = text.split("Promoted")[0].strip()
                        job_info["job_priority"] = "High"
                    else:
                        job_info["applicants"] = text
                    continue
                
                # Promotion (standalone)
                if "promoted" in low and job_info["job_priority"] == "Low":
                    job_info["job_priority"] = "High"
                    continue
                
                # Application status
                if not job_info["application_status"]:
                    if ("response" in low or "reviewing" in low or "company review" in low):
                        job_info["application_status"] = text
                        continue

                # Generic fallback: catch any green positive text
                if not job_info["application_status"]:
                    span_class = span.get_attribute("class") or ""
                    if "tvm__text--text-positive" in span_class:
                        job_info["application_status"] = text
                        continue
                
                # Posted date
                if not job_info["posted_date"] and any(w in low for w in ["ago", "minute", "hour", "day", "week", "month"]):
                    job_info["posted_date"] = text
                    continue
                
                # Location (fallback - whatever is left)
                if not job_info["job_location"]:
                    job_info["job_location"] = text
                else:
                    print(f"    ⚠️ Unmatched text: '{text}'")
            
            # Extract company review time (green text - separate element)
            review_container = page.query_selector("span.job-details-jobs-unified-top-card__company-review-text")
            if review_container:
                review_text = review_container.text_content().strip()
                if review_text:
                    job_info["application_status"] = review_text
            
        else:
            print("❌ ERROR: Container not found!")

    except Exception as e:
        print(f"\n❌ EXCEPTION CAUGHT: {e}")
        import traceback
        traceback.print_exc()
        
        job_info["job_location"] = ""
        job_info["posted_date"] = ""
        job_info["applicants"] = ""
        job_info["job_priority"] = "Low"
        job_info["application_status"] = ""
    
    human_wait(1,2)
    try:
        job_detail_class = page.query_selector_all("div.job-details-fit-level-preferences strong")

        job_info["salary"] = ""
        job_info["job_working_des"] = ""
        job_info["job_type"] = ""

        value = []
        if job_detail_class:
            for element in job_detail_class:
                raw_text = element.text_content()
                if raw_text:
                    cleaned = raw_text.strip()
                    if cleaned:
                        value.append(cleaned)
            if len(value) == 1:
                job_info["job_type"] = value[0]
            
            elif len(value) == 3 :
                job_info["salary"] = value[0]
                job_info["job_type"] = value[1]
                job_info["job_working_des"] = value[2]
            else:
                job_info["job_working_des"] = value[0]
                job_info["job_type"] = value[1]
        else:
            job_info["salary"] = ""
            job_info["job_type"] = ""
            job_info["job_working_des"] = ""
    except Exception as e:
        print(f"⚠️ Error extracting job details: {e}")
        job_info["salary"] = ""
        job_info["job_working_des"] = ""
        job_info["job_type"] = ""

    human_wait(1,2)
    try:
        company_official_detail_class = page.query_selector("div.t-14.mt5")
        if company_official_detail_class:
            company_sector = company_official_detail_class.text_content().strip()
        else:
            company_sector = ""

        job_info["company_sector"] = company_sector
    except:
        job_info["company_sector"] = ""
    
    human_wait(1,2)
    try:
        company_employee_detail = page.query_selector_all("div.t-14.mt5 span")
        if len(company_employee_detail) == 1:
            # Only total employees available
            company_total_employee_text = company_employee_detail[0].text_content().strip()

            if not company_total_employee_text:
                pseudo_data = page.evaluate("""
                    () => {
                        const span = document.querySelector('div.t-14.mt5 span');
                        return span ? window.getComputedStyle(span, '::before').content.replace(/['"]/g, '') : '';
                    }
                """)
                company_total_employee = pseudo_data
            else:
                company_total_employee = company_total_employee_text

            job_info["company_total_employee"] = company_total_employee
            job_info["company_employee_on_linkedin"] = ""
            
            print(f"   👥 Total employees: '{company_total_employee}' (LinkedIn count not shown)")
            
        elif len(company_employee_detail) == 2:
            # Both total employees and LinkedIn employees available
            company_total_employee = company_employee_detail[0].text_content().strip()
            company_employee_on_linkedin = company_employee_detail[1].text_content().strip()
            if not company_total_employee:
                company_total_employee = page.evaluate("""
                    () => {
                        const span = document.querySelector('div.t-14.mt5 span');
                        return span ? window.getComputedStyle(span, '::before').content.replace(/['"]/g, '') : '';
                    }
                """)
                
            job_info["company_total_employee"] = company_total_employee
            job_info["company_employee_on_linkedin"] = company_employee_on_linkedin
            
            print(f"   👥 Total employees: '{company_total_employee}'")
            print(f"   📊 On LinkedIn: '{company_employee_on_linkedin}'")
            
        else:
            print("   ❌ No employee data spans found")
            job_info["company_total_employee"] = ""
            job_info["company_employee_on_linkedin"] = ""

    except Exception as e:
        print(f"   ❌ Error extracting employee data: {e}")
        job_info["company_total_employee"] = ""
        job_info["company_employee_on_linkedin"] = ""

    try:
        jd_class = page.query_selector("div.jobs-box__html-content#job-details")
        if jd_class:
            # Get inner HTML to preserve structure
            jd_html = jd_class.inner_html()
            # Or get clean text content
            jd = jd_class.text_content().strip()
            
            # Remove extra whitespace and clean up
            import re
            jd = re.sub(r'\s+', ' ', jd)  # Replace multiple spaces/newlines with single space
            jd = re.sub(r'\n\s*\n', '\n', jd)  # Remove multiple blank lines
            jd = jd.strip()
        else:
            jd = ""
        
        job_info["jd"] = jd
        print(f"✓ Job Description: {len(jd)} characters extracted")
        print(f"Preview: {jd[:200]}...")  # Show first 200 chars
        
    except Exception as e:
        print(f"✗ Error extracting job description: {e}")
        job_info["jd"] = ""

    return job_info

def process_single_page(page, page_num, all_rows, domain_name):
    """Process all jobs on a single page"""
    print(f"\n🔍 Processing Page {page_num}...")
    
    # Wait for page to load
    time.sleep(0.5)
    
    # Check if we have reached a page with no jobs
    try:
        page.wait_for_selector("li.scaffold-layout__list-item", timeout=15000)
    except:
        print(f"   ❌ No jobs found on page {page_num}")
        return 0
    
    # Get total job count (only on first page)
    if page_num == 1:
        total_jobs = get_total_job_count(page)
        if total_jobs:
            print(f"   📊 Total jobs available: {total_jobs:,}")
    
    # Scroll to load all jobs on this page
    jobs_on_page = scroll_page(page, pause=2, max_scroll=15)
    
    if jobs_on_page == 0:
        print(f"   ⚠️ No jobs loaded on page {page_num}")
        return 0
    
    # Get all job cards
    cards = page.query_selector_all("li.scaffold-layout__list-item div.job-card-container")
    print(f"   📋 Found {len(cards)} job cards on page {page_num}")
    
    page_jobs_processed = 0
    
    # Process each job on this page
    for i, card in enumerate(cards):
        job_number = len(all_rows) + 1
        print(f"\n   📋 Processing job {job_number} (Page {page_num}, Card {i+1}/{len(cards)})...")

        if click_job_card(page, i):
            print(f"      ✅ Clicked job card {i+1}")
            human_wait(1,2)
            job_data = extract_job_info(page)
            
            if job_data.get('job_title'):  # Only add if we got valid data
                job_data['scrapped_at'] = time.strftime("%Y-%m-%d")
                job_data['domain'] = domain_name
                all_rows.append(job_data)
                page_jobs_processed += 1
                print(f"      📊 ✅ Job data extracted successfully")
            else:
                print(f"      ❌ Failed to extract job data")
        else:
            print(f"      ❌ Failed to click job card {i+1}")
            continue
    
    print(f"   ✅ Page {page_num} complete: {page_jobs_processed}/{len(cards)} jobs processed")
    return page_jobs_processed

def main():

    OUTPUT_DIRECTORY = r"C:\Users\gis28\.webscrap\dags\output"

    os.makedirs(OUTPUT_DIRECTORY, exist_ok=True)

    state_file_path = os.path.join(OUTPUT_DIRECTORY, STATE_FILE)
    output_csv_path = os.path.join(OUTPUT_DIRECTORY, OUTPUT_CSV)

    print(f"📂 Output directory: {OUTPUT_DIRECTORY}")
    print(f"💾 State file: {state_file_path}")
    print(f"📄 CSV output: {output_csv_path}")

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
            context = browser.new_context(storage_state=state_file_path) 
            page = context.new_page()
        else:
            context = browser.new_context()
            page = context.new_page()
            page.goto("https://www.linkedin.com/login")
            input("🔑 Please log in manually, then press Enter here...")
            context.storage_state(path=state_file_path)  # Save cookies + local storage

        # page = context.new_page()

        all_rows = []
        for domain_name, url_key in DOMAINS:
            print(f"Scraping {domain_name}...")

            SEARCH_URL = SEARCH_URL_TEMP.format(url_key)
            current_page = 1

            print(f"🚀 Starting LinkedIn job scraping (max {MAX_PAGES} pages)...")

            while current_page <= MAX_PAGES:
                # Generate URL for current page
                page_url = get_page_url(SEARCH_URL, current_page)
                print(f"\n📄 Navigating to page {current_page}...")
                print(f"   🔗 URL: {page_url}")

                try:
                    page.goto(page_url, timeout=60000, wait_until="domcontentloaded")
                except Exception as e:
                    print(f"   ❌ Navigation to page {current_page} failed: {e}")
                    break

                # Check if this page has jobs
                try:
                    # Wait for either job results or no-results message
                    page.wait_for_selector("li.scaffold-layout__list-item, div.jobs-search-no-results-banner", timeout=15000)
                    
                    # Check if we've reached the end
                    no_results = page.query_selector("div.jobs-search-no-results-banner")
                    if no_results:
                        print(f"   ℹ️ No more jobs available (reached end at page {current_page})")
                        break
                        
                except:
                    print(f"   ⚠️ Page {current_page} failed to load properly")
                    break

                # Process jobs on this page
                jobs_processed = process_single_page(page, current_page, all_rows, domain_name)
                
                if jobs_processed == 0:
                    print(f"   ⚠️ No jobs processed on page {current_page}, stopping...")
                    break

                # Check if more pages are available
                if current_page < MAX_PAGES:
                    has_more_pages = check_pagination_available(page)
                    if not has_more_pages:
                        print(f"   ℹ️ No more pages available after page {current_page}")
                        break

                current_page += 1
                human_wait(1, 2)  # Wait between pages

        # Save all collected data
        if all_rows:
            fieldnames = [
                "company_name", "company_page_link", "company_logo", "job_title", "job_link",
                "job_location", "posted_date", "applicants", "job_priority", "application_status",
                "salary", "job_type", "job_working_des", "company_sector", "company_total_employee", 
                "company_employee_on_linkedin","jd", "scrapped_at", "domain"
            ]

            with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(all_rows)
            
            print(f"\n🎉 Scraping completed!")
            print(f"   📊 Total jobs scraped: {len(all_rows)}")
            print(f"   📄 Pages processed: {current_page - 1}")
            print(f"   💾 Data saved to: {output_csv_path}")
        else:
            print("\n⚠️ No jobs were scraped!")

        context.close()
        browser.close()

if __name__ == "__main__":
    main()



