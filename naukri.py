from playwright.sync_api import sync_playwright
import csv
import time
import random
import json
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import os

BASE_URL_TEMPLATE = "https://www.naukri.com/{}-jobs-in-india"

DOMAINS = [
    ("Frontend Development", "frontend-development"),
    ("Software Engineer", "software-engineering"),
    ("Data Analyst", "data-analyst"),
    ("Data Engineer", "data-engineer"),
    ("Cyber Security", "cyber-security"),
    ("Backend Development", "backend-development"),
    ("Full Stack Development", "full-stack-development"),
    ("DevOps Engineer", "devops-engineer"),
    ("Cloud Computing", "cloud-computing"),
    ("Big Data Engineer", "big-data-engineer"),
    ("Data Scientist", "data-scientist"),
    ("Business Analyst", "business-analyst"),
    ("AI Engineer", "ai-engineer"),
    ("ML Engineer", "ml-engineer"),
    ("Deep Learning", "deep-learning"),
    ("Mobile App Development", "mobile-app-development"),
    ("Android Development", "android-development"),
    ("Internet of Things", "internet-of-things"),
    ("Database Administrator", "database-administrator"),
    ("QA Engineer", "qa-engineer"),
    ("Automation Testing", "automation-testing"),
    ("Site Reliability Engineer", "site-reliability-engineer"),
    ("Product Manager", "product-manager"),
    ("UI UX Designer", "ui-ux-designer")
]

SATE_FILE = "naukri_state.json"
OUTPUT_CSV = "naukri.csv"
max_page = 2

def human_wait(min_s = 1.0, max_s = 3.0):
    time.sleep(random.uniform(min_s, max_s))

def scroll_page(page, pause=2.0, max_scroll=15):
    """
    Simplified scrolling function for Naukri.com - more reliable approach
    """
    print("Starting scroll to load all job cards...")
    
    prev_count = 0
    no_change_iterations = 0
    
    for i in range(max_scroll):
        # Get current job count
        cards = page.locator("div.srp-jobtuple-wrapper")
        current_count = cards.count()
        
        print(f"[{i+1}] Current jobs: {current_count}")
        
        # Try different scrolling strategies
        try:
            if i < 3:
                # Initial scrolls - use page scrolling
                page.evaluate("window.scrollBy(0, 1000)")
            elif no_change_iterations == 0:
                # Medium scrolls - scroll to bottom of visible area
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            else:
                # Final attempts - try container scrolling
                job_container = page.locator("div.styles_job-listing-container").first
                if job_container.count() > 0:
                    job_container.evaluate("el => el.scrollTop = el.scrollHeight")
                else:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        
        except Exception as e:
            print(f"   ⚠️ Scroll error: {e}")
            # Fallback to basic page scroll
            page.evaluate("window.scrollBy(0, 1000)")
        
        # Wait for content to load
        time.sleep(pause)
        
        # Check if new jobs loaded
        new_cards = page.locator("div.srp-jobtuple-wrapper")
        new_count = new_cards.count()
        
        if new_count > prev_count:
            print(f"   ✅ Loaded {new_count - prev_count} new jobs")
            prev_count = new_count
            no_change_iterations = 0
        else:
            no_change_iterations += 1
            print(f"   ⏸️ No new jobs loaded (attempt {no_change_iterations})")
        
        # Stop if no new jobs for 3 consecutive attempts
        if no_change_iterations >= 3:
            print("   🛑 No more jobs loading, stopping scroll")
            break
    
    print(f"✅ Scrolling complete. Total jobs loaded: {prev_count}")
    return prev_count

def get_page_url(base_url, page_number):
    
    parsed = urlparse(base_url)
    path = parsed.path

    if path.split("-")[-1].isdigit():
        base_path = "-".join(path.split("-")[:-1])
    else:
        base_path = path
    
    if page_number == 1:
        new_path = base_path
    else:
        new_path = f"{base_path}-{page_number}"
    
    new_url = f"{parsed.scheme}://{parsed.netloc}{new_path}"

    if parsed.query:
        new_url += f"?{parsed.query}"

    return new_url

def get_total_job_count(page):
    try:
        job_count_text = page.query_selector("div.styles_h1-wrapper__mHVA1")
        if job_count_text:
            text = job_count_text.text_content().strip()

            parts = text.split("of")

            if len(parts)>1:
                count_str = parts[1].strip().split()[0]
                return int(count_str.replace(",",""))
    except Exception as e:
        print(f"⚠️ Failed to extract total job count: {e}")
    return None

def extract_job_info(new_tab):
    human_wait(1,2)
    job_info = {}

    try:
        job_title_class = new_tab.query_selector("div.styles_jhc__jd-top-head__MFoZl h1")
        if job_title_class:
            job_title = job_title_class.text_content().strip()
        else:
            print(f"no job_title here")
            job_title = ""
        job_info["job_title"] = job_title
    
    except:
        job_info["job_title"] = ""
    
    try:
        company_name_class = new_tab.query_selector("div.styles_jd-header-comp-name__MvqAI a")
        if company_name_class:
            job_link = company_name_class.get_attribute("href")
            company_name = company_name_class.text_content().strip()
        else:
            print(f"No job_link and company_name")
            job_link = ""
            company_name = ""
        
        job_info["job_link"] = job_link
        job_info["company_name"] = company_name
    except:
        job_info["job_link"] = ""
        job_info["company_name"] = ""

    try:
        company_link = new_tab.query_selector(
            "a:has(img[alt='Company Logo'])"
            )
        
        if company_link:
            company_page_link = company_link.get_attribute("href")
        else:
            company_page_link = ""
        
        job_info['company_page_link'] = company_page_link
    
    except:
        job_info['company_page_link'] = ""
    
    try:
        rating_class = new_tab.query_selector("div.styles_rating-wrapper__jPmOo span")
        if rating_class:
            company_rating = rating_class.text_content().strip()
        else:
            print(f"no rating")
            company_rating = ""
        job_info["company_rating"] = company_rating
    except:
        job_info["company_rating"] = ""
    
    try:
        experience_class = new_tab.query_selector("div.styles_jhc__exp__k_giM span")
        if experience_class:
            experience = experience_class.text_content().strip()
        else:
            experience = "" 
        job_info["experience"] = experience
    except:
        job_info["experience"] = ""
    
    try:
        salary_class = new_tab.query_selector("div.styles_jhc__salary__jdfEC span")
        if salary_class:
            salary = salary_class.text_content().strip()
        else:
            print(f"no salary")
            salary = ""
        job_info["salary"] = salary
    except:
        job_info["salary"] = "" 
    
    try:
        location_class = new_tab.query_selector("div.styles_jhc__loc___Du2H span")
        if location_class:
            location = location_class.text_content().strip()
        else:
            print(f"no location")
            location = ""
        job_info["location"] = location
    except:
        job_info["location"] = ""

    try:
        span_class = new_tab.query_selector_all("span.styles_jhc__stat__PgY67")
        
        job_info["posted"] = ""
        job_info["openings"] = ""
        job_info["applicants"] = ""

        for span in span_class:
            label_elem = span.query_selector("label")
            value_elem = span.query_selector("span")

            if label_elem and value_elem:

                label = label_elem.text_content().strip().lower()
                value = value_elem.text_content().strip()

                if label == "posted:":
                    job_info["posted"] = value
                elif label == "openings:":
                    job_info["openings"] = value
                else:
                    job_info["applicants"] = value
                
            else:
                print(f"{label_elem} not found")
    
    except Exception as e:
        print(f"❌ Error extracting job stats: {e}")
        job_info["posted"] = ""
        job_info["openings"] = ""
        job_info["applicants"] = ""

    try:
        print("🔍 Starting job description extraction...")
        
        # More specific selectors for Naukri job description
        jd_selectors = [
            "div[class*='styles_JDC']",
            "div[class*='job-description']", 
            "section[class*='job-desc']",
            ".job-description",
            "[data-testid*='job-description']",
            "div.styles_JDC__dang-inner-html__h0K4t"
        ]
        
        jd_container = None
        
        # Find the job description container
        for selector in jd_selectors:
            try:
                container = new_tab.query_selector(selector)
                if container:
                    jd_container = container
                    print(f"✅ Found JD container with selector: {selector}")
                    break
            except Exception as e:
                continue
        
        if not jd_container:
            print("❌ No job description container found")
            job_info["job_description"] = "Not available"
            return job_info
        
        # Get both HTML and text content to better parse structure
        container_html = jd_container.inner_html()
        container_text = jd_container.text_content()
        
        html_parts = container_html.split('<')
        
        # Extract text while preserving structure markers
        structured_lines = []
        current_text = ""
        
        for part in html_parts:
            if '>' in part:
                tag_and_content = part.split('>', 1)
                if len(tag_and_content) > 1:
                    content = tag_and_content[1].strip()
                    if content:
                        # Check if this looks like a heading (short and contains key terms)
                        if (len(content) < 100 and 
                            any(term in content.lower() for term in [
                                'role', 'responsibilities', 'preferred', 'candidate', 
                                'profile', 'requirements', 'qualification', 'education'
                            ])):
                            # This might be a section heading
                            if current_text:  # Save previous content
                                structured_lines.append(current_text.strip())
                                current_text = ""
                            structured_lines.append(content)  # Add heading as separate line
                        else:
                            # Regular content - append to current text
                            if current_text:
                                current_text += " " + content
                            else:
                                current_text = content
        
        # Add any remaining text
        if current_text:
            structured_lines.append(current_text.strip())
        
        # If structured parsing didn't work well, try text-based approach
        if len(structured_lines) < 3:  # If we didn't get good structure
            print("🔄 HTML parsing didn't work well, trying text-based approach...")
            
            # Look for section markers in the text
            text_lower = container_text.lower()
            
            # Find section boundaries
            section_markers = [
                'preferred candidate profile',
                'required candidate profile',
                'candidate profile',
                'requirements',
                'qualifications'
            ]
            
            # Split at the first found section marker
            split_text = container_text
            split_point = -1
            found_marker = ""
            
            for marker in section_markers:
                idx = text_lower.find(marker)
                if idx != -1 and (split_point == -1 or idx < split_point):
                    split_point = idx
                    found_marker = marker
            
            if split_point != -1:
                # Split the text at this point
                jd_part = split_text[:split_point].strip()
                remaining_part = split_text[split_point:].strip()
                
                print(f"✂️ Split at '{found_marker}' (position {split_point})")
                print(f"📝 JD part length: {len(jd_part)}")
                print(f"📝 Remaining part: {remaining_part[:100]}...")
                
                structured_lines = [line.strip() for line in jd_part.split('\n') if line.strip()]
                if not structured_lines:  # If no line breaks, treat as single line
                    structured_lines = [jd_part]
            else:
                # No section markers found, use original approach
                structured_lines = [line.strip() for line in container_text.split('\n') if line.strip()]
        
        lines = structured_lines
        for i, line in enumerate(lines):
            print(f"  Line {i}: '{line[:100]}{'...' if len(line) > 100 else ''}')")
        
        # Try to find "Job description" heading
        jd_heading_idx = -1
        for i, line in enumerate(lines):
            if "job description" in line.lower() and len(line) < 100:
                jd_heading_idx = i
                break
        
        # Handle cases with or without explicit "Job description" heading
        if jd_heading_idx == -1:
            
            # If no explicit heading, treat the entire container as potential JD content
            # But first check if it actually looks like job description content
            full_text = ' '.join(lines).lower()
            
            # Keywords that indicate this might be job description content
            jd_indicators = [
                'hiring', 'looking for', 'required', 'experience', 'qualification', 
                'skills', 'candidate', 'position', 'role', 'responsibilities',
                'job', 'vacancy', 'opening', 'apply'
            ]
            
            has_jd_indicators = any(indicator in full_text for indicator in jd_indicators)
            
            if not has_jd_indicators:
                print("❌ Content doesn't appear to be job description")
                job_info["job_description"] = "Not available"
                return job_info
            
            print("✅ Content appears to be job description, processing entire container")
            remaining_lines = lines
        else:
            # Get content after "Job description" heading
            remaining_lines = lines[jd_heading_idx + 1:]
        
        if not remaining_lines:
            print("❌ No content found after 'Job description' heading")
            job_info["job_description"] = "Not available"
            return job_info

        for i, line in enumerate(remaining_lines[:5]):  # Show first 5 lines for debug
            print(f"  Line {i}: '{line}'")
        
        # Check what comes immediately after "Job description"
        first_line = remaining_lines[0]
        
        # Define common subheadings that can appear under Job description
        subheadings = [
            "role & responsibilities",
            "role and responsibilities", 
            "responsibilities",
            "key responsibilities",
            "duties",
            "job duties",
            "what you'll do",
            "job overview",
            "position overview",
            "about the role",
            "job profile",
            "description",
            "overview"
        ]
        
        # Check if first line is a subheading
        is_first_line_subheading = False
        for subheading in subheadings:
            if (first_line.lower().strip() == subheading or 
                first_line.lower().strip() == subheading + ":" or
                first_line.lower().strip().startswith(subheading)):
                is_first_line_subheading = True
                print(f"✅ First line is subheading: '{first_line}'")
                break
        
        extracted_content = []
        
        if is_first_line_subheading:
            # CONDITION 2: First line is a subheading - extract only that subheading's content
            print("📝 CONDITION 2: Subheading found - extracting subheading content only")
            
            # Add the subheading
            extracted_content.append(first_line)
            
            # Extract content under this subheading until next major section
            stop_keywords = [
                "preferred candidate profile",
                "required candidate profile", 
                "candidate profile",
                "requirements",
                "qualifications",
                "preferred qualifications",
                "skills required",
                "experience required",
                "education",
                "what we offer",
                "benefits",
                "role:",
                "industry type:",
                "department:",
                "employment type:",
                "key skills",
                "other details"
            ]
            
            for line in remaining_lines[1:]:  # Skip the subheading itself
                line_clean = line.strip()
                line_lower = line_clean.lower()
                
                print(f"🔍 Processing line: '{line_clean}'")  # Debug line
                
                # Check if this line starts a new major section
                should_stop = False
                for keyword in stop_keywords:
                    # More precise matching to avoid false positives
                    if (line_lower == keyword or 
                        line_lower == keyword + ":" or
                        (line_lower.startswith(keyword) and len(line_clean) < 100)):  # Avoid stopping on long sentences
                        should_stop = True
                        print(f"🛑 Stopped at section: '{line_clean}' (matched keyword: '{keyword}')")
                        break
                
                if should_stop:
                    break
                
                # Add content line (only if it's not empty)
                if line_clean:
                    extracted_content.append(line_clean)
                    print(f"✅ Added line: '{line_clean}'")  # Debug line
        
        else:
            # CONDITION 1: First line is direct paragraph - extract only until first subheading/section
            print("📝 CONDITION 1: Direct paragraph found - extracting paragraph only")
            
            # All possible headings/sections that could appear after direct content
            all_section_keywords = subheadings + [
                "preferred candidate profile",
                "required candidate profile",
                "candidate profile", 
                "requirements",
                "qualifications",
                "preferred qualifications",
                "skills required",
                "experience required",
                "education",
                "what we offer",
                "benefits",
                "role:",
                "industry type:",
                "department:",
                "employment type:",
                "key skills",
                "other details"
            ]
            
            for line in remaining_lines:
                line_lower = line.strip().lower()
                
                # Check if this line is a heading/section
                is_heading = False
                for keyword in all_section_keywords:
                    if (line_lower == keyword or 
                        line_lower == keyword + ":" or
                        line_lower.startswith(keyword)):
                        is_heading = True
                        print(f"🛑 Stopped at heading: '{line}'")
                        break
                
                if is_heading:
                    break
                
                # Add content line
                if line.strip():
                    extracted_content.append(line)
        
        # Process extracted content
        if extracted_content:
            jd_text = '\n'.join(extracted_content).strip()
            
            # Clean up HTML entities and formatting
            import html
            jd_text = html.unescape(jd_text)  # Convert &amp; to &, etc.
            
            # Clean up bullet points and formatting
            lines = jd_text.split('\n')
            cleaned_lines = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # Handle bullet points - split on common patterns
                if any(pattern in line for pattern in ['Handle customer', 'Take orders', 'Follow-up', 'Good Communication', 'Freshers are', 'Make Outbound', 'Explain product']):
                    # This line contains multiple bullet points concatenated
                    # Split them based on capital letter patterns
                    import re
                    
                    # Split on patterns like "letterHandle", "letterTake", etc.
                    bullet_pattern = r'([a-z])([A-Z][a-z])'
                    split_line = re.sub(bullet_pattern, r'\1\n• \2', line)
                    
                    # Also split on common starting patterns
                    for pattern in ['Handle ', 'Take ', 'Follow-up ', 'Good ', 'Freshers ', 'Make ', 'Explain ']:
                        split_line = split_line.replace(pattern, '\n• ' + pattern)
                    
                    # Clean up and add the split lines
                    for subline in split_line.split('\n'):
                        subline = subline.strip()
                        if subline and subline != '•':
                            if not subline.startswith('• '):
                                cleaned_lines.append(subline)
                            else:
                                cleaned_lines.append(subline)
                else:
                    # Regular line
                    cleaned_lines.append(line)
            
            # Join with spaces instead of line breaks for a single line output
            jd_text = ' '.join(cleaned_lines)
            
            # Final cleanup - remove extra spaces
            import re
            jd_text = re.sub(r' +', ' ', jd_text)  # Remove multiple spaces
            jd_text = jd_text.strip()
            
            # Validate content
            if len(jd_text.strip()) < 10:
                print("⚠️ Extracted content too short")
                job_info["job_description"] = "Not available"
            else:
                # Limit length if too long
                if len(jd_text) > 1500:
                    jd_text = jd_text[:1500] + "..."
                
                job_info["job_description"] = jd_text
                print(f"✅ Successfully extracted {len(jd_text)} characters")
                print(f"📋 Cleaned content preview:")
        else:
            print("❌ No content extracted")
            job_info["job_description"] = "Not available"
            
    except Exception as e:
        print(f"❌ Error extracting job description: {e}")
        import traceback
        traceback.print_exc()
        job_info["job_description"] = "Not available"
    
    try:
        des_class = new_tab.query_selector_all("div.styles_details__Y424J")

        job_info["job_role"] = ""
        job_info["industry_type"] = ""
        job_info["department"] = ""
        job_info["job_type"] = ""
        job_info["job_working_des"] = ""
        job_info["role_category"] = ""

        for des in des_class:
            label_elem = des.query_selector("label")
            value_elem = des.query_selector("span a, span")

            if label_elem and value_elem:
                label = label_elem.text_content().strip().lower()
                value = value_elem.text_content().strip()

                if label == "role:":
                    job_info["job_role"] = value
                elif label == "industry type:":
                    job_info["industry_type"] = value
                elif label == "department:":
                    job_info["department"] = value
                elif label == "employment type:":

                    emp_text = value.split(',')

                    text = []
                    for emp in emp_text:
                        text.append(emp)

                    if len(text) > 0:
                        job_type = text[0]
                        
                    if len(text) > 1:
                        job_working_des = text[1]

                    job_info["job_type"] = job_type
                    job_info["job_working_des"] = job_working_des
                else:
                    job_info["role_category"] = value
            
            else:
                print(f"{label_elem} not found")

    except Exception as e:
        print(f"❌ Error extracting job stats: {e}")

    try:
        job_info["skill"] = ""

        skill_container = new_tab.query_selector("div[class*='styles_key-skill__GIPn_']")

        if skill_container:
            skill_divs = skill_container.query_selector_all("div")

            print(f"Found {len(skill_divs)} skill divs")

            if len(skill_divs) == 2:

                non_starred_div = skill_divs[1]

                skill_elements = non_starred_div.query_selector_all("span")

                non_starred_skills = []

                for elem in skill_elements:
                    skill_text = elem.text_content().strip()
                    if skill_text and len(skill_text) > 1:
                        non_starred_skills.append(skill_text)
                
                print(f"Non-starred skills from div[3]: {non_starred_skills}")

                if non_starred_skills:
                    job_info["skill"] = ",".join(non_starred_skills)
            
            elif len(skill_divs) == 4:
                non_starred_div = skill_divs[3]

                skill_elements = non_starred_div.query_selector_all("span")

                non_starred_skills = []

                for elem in skill_elements:
                    skill_text = elem.text_content().strip()
                    if skill_text and len(skill_text) > 1:
                        non_starred_skills.append(skill_text)
                
                print(f"Non-starred skills from div[3]: {non_starred_skills}")

                if non_starred_skills:
                    job_info["skill"] = ",".join(non_starred_skills)
            else:
                print(f"Expected 4 divs, found {len(skill_divs)}")
        
        else:
            print("Skills container not found")

    except Exception as e:
        print(f"❌ Error: {e}")

    try:
        job_info["logo_link"] = ""
        
        # Directly select the img with the specific class
        logo_img = new_tab.query_selector("div.styles_jhc__top__BUxpc img.styles_jhc__comp-banner__ynBvr")
        
        if logo_img:
            logo_link = logo_img.get_attribute("src")
            job_info["logo_link"] = logo_link
            print(f"Logo image URL: {logo_link}")
        else:
            print("Logo image not found")

    except Exception as e:
        print(f"❌ Error extracting logo link: {e}")
    
    return job_info

def click_job_link(context,page, card_index):
    try:
        new_page_class = page.query_selector_all("div.srp-jobtuple-wrapper")
        if card_index < len(new_page_class):
            card = new_page_class[card_index]
            link_element = card.query_selector("a.title")
            if link_element:
                with context.expect_page() as new_page_info:
                    link_element.click()
                
                new_page = new_page_info.value
                new_page.wait_for_load_state("domcontentloaded")

                job_data = extract_job_info(new_page)

                new_page.close()

                return job_data
        return False
    except Exception as e:
        print(f"   ❌ Error clicking job card {card_index}: {e}")
        return False

def process_single_page(context,page, page_num, all_rows, domain_name):
    print(f"\n🔍 Processing Page {page_num}...")

    human_wait(1,2)

    try:
        page.wait_for_selector("div.srp-jobtuple-wrapper", timeout = 15000)
    except:
        print(f"   ❌ No jobs found on page {page_num}")
        return 0

    if page_num == 1:
        total_jobs = get_total_job_count(page)
        if total_jobs:
            print(f"   📊 Total jobs available: {total_jobs:,}")
    
    jobs_on_page = scroll_page(page, pause = 2, max_scroll = 15)

    if jobs_on_page == 0:
        print(f"   ⚠️ No jobs loaded on page {page_num}")
        return 0
    
    cards = page.query_selector_all("div.srp-jobtuple-wrapper")
    print(f"   📋 Found {len(cards)} job cards on page {page_num}")

    page_jobs_processed = 0

    for i , card in enumerate(cards):
        job_number = len(all_rows)+1
        print(f"\n   📋 Processing job {job_number} (Page {page_num}, Card {i+1}/{len(cards)})...")

        job_data = click_job_link(context, page, i)

        if job_data and job_data.get("job_title"):
            job_data["domain"] = domain_name
            job_data["scrapped_at"] = time.strftime("%Y:%m:%d")
            all_rows.append(job_data)
            page_jobs_processed += 1
            print("      📊 ✅ Job data extracted successfully")
        else:
            print(f"      ❌ Failed to extract job {i+1}")

        human_wait(1, 2)
    print(f"   ✅ Page {page_num} complete: {page_jobs_processed}/{len(cards)} jobs processed")
    return page_jobs_processed

def check_pagination_available(page):
    try:
        next_button = page.query_selector("a.styles_btn-secondary__2AsIP:has-text('Next')")
        if next_button:
            return True
        
        # Method 2: Check pagination numbers
        pagination = page.query_selector("div.styles_pages__v1rAK")
        if pagination:
            page_links = pagination.query_selector_all("a")
            if len(page_links) > 1:  # More than one page link exists
                return True

        # Method 3: Check "no jobs" message
        no_results = page.query_selector("div.styles_noResultContainer__...")
        if no_results:
            return False

        return False
    except Exception as e:
        print(f"   ⚠️ Error checking pagination: {e}")
        return False
        
def main():

    OUTPUT_DIRECTORY = r"C:\Users\gis28\.webscrap\dags\output"

    os.makedirs(OUTPUT_DIRECTORY, exist_ok= True)

    state_file_path = os.path.join(OUTPUT_DIRECTORY, SATE_FILE)
    output_csv_path = os.path.join(OUTPUT_DIRECTORY, OUTPUT_CSV)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless = False)
        # if state_file:
        #     context = browser.new_context(storage_state = state_file)
        # else:
        context = browser.new_context()
        page = context.new_page()

        all_rows = []
        for domain_name, url_key in DOMAINS:
            print(f"Scraping {domain_name}...")

            BASE_SEARCH_URL = BASE_URL_TEMPLATE.format(url_key)

            current_page = 1

            print(f"🚀 Starting Naukri job scraping (max {max_page} pages)...")

            while current_page <= max_page:
                page_url = get_page_url(BASE_SEARCH_URL, current_page)
                print(f"\n📄 Navigating to page {current_page}...")
                print(f"   🔗 URL: {page_url}")

                try:
                    page.goto(page_url, timeout=60000, wait_until="domcontentloaded")
                    human_wait(2, 4)
                except Exception as e:
                    print(f"   ❌ Navigation to page {current_page} failed: {e}")
                    break
                
                try:
                    page.wait_for_selector("div.srp-jobtuple-wrapper,div.noJResult", timeout=15000)

                    no_results = page.query_selector("div.noJResult, section.no-jobs-container")
                    if no_results:
                        print(f"   ℹ️ No more jobs available (reached end at page {current_page})")
                        break
                except:
                    print(f"   ⚠️ Page {current_page} failed to load properly")
                    break

                jobs_processed = process_single_page(context,page, current_page, all_rows, domain_name)
                if jobs_processed == 0:
                    print(f"   ⚠️ No jobs processed on page {current_page}, stopping...")
                    break

                if current_page < max_page:
                    has_more_pages = check_pagination_available(page)
                    if not has_more_pages:
                        print(f"   ℹ️ No more pages available after page {current_page}")
                        break
                
                current_page +=1
                human_wait(1,2)
        
        if all_rows:
            fieldnames = [
                "job_title", "job_link", "company_name", "company_page_link","company_rating", 
                "experience", "salary", "location", "posted", "openings", 
                "applicants", "job_description", "job_role", "industry_type",
                "department", "job_type", "job_working_des", "role_category", "skill", 
                "logo_link", "scrapped_at", "domain"
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