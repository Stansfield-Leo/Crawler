# Crawler

Course Slides Crawler and Organizer

A small Python toolkit for downloading and reorganizing course materials from Moodle and other course websites.

The project contains two scripts:

course_slides_crawler.py recursively visits course pages and downloads supported teaching files.

organize_course_slides.py reorganizes downloaded files by course code and, optionally, by teaching week.

The crawler is designed for pages that require JavaScript and university single sign-on. It uses Playwright with a persistent browser profile so that the user can complete authentication manually in a normal browser window.

This project is intended only for materials that you are authorized to access and retain. It must not be used to bypass authentication, evade access controls, collect private student data, or redistribute copyrighted teaching materials.

Features

Course crawler

Supports Moodle and ordinary course websites.

Supports JavaScript-rendered pages.

Supports manual university login and Microsoft/UCL single sign-on redirects.

Recursively follows course-page links.

Downloads:

.ppt

.pptx

.pps

.ppsx

.pdf

Detects downloadable files from:

file extensions;

HTTP content types;

download headers;

PDF and PowerPoint file signatures.

Avoids downloading identical files more than once using SHA-256 hashes.

Stores download metadata in download_manifest.csv.

Supports multiple starting URLs.

Supports additional approved domains, such as a university SharePoint site.

Allows limits on crawl depth, page count, file size, delay, and timeout.

Course organizer

Reads download_manifest.csv.

Detects course codes such as COMP0249.

Creates one folder per course.

Optionally creates Week_01, Week_02, and similar subfolders.

Copies files by default, preserving the original download directory.

Can move files instead of copying them.

Can exclude coursework, assignments, submissions, quizzes, and other assessment files.

Can keep only PowerPoint files or include PDFs.

Generates organize_manifest.csv.

Repository Structure

```text
course-slides-toolkit/
│
├── course_slides_crawler.py
│
├── organize_course_slides.py
│
├── README.md
│
└── .gitignore
```

Do not commit downloaded course files, browser profiles, authentication data, or generated manifests.

A suitable .gitignore is:

# Browser profiles and authentication state
.course_crawler_profile/
course_crawler_profile/
course_crawler_profile*/
playwright/.auth/
auth.json
storage_state.json

# Downloaded materials
Master_Slides/
Organized_Courses/
master_slides/
organized_courses/

# Generated manifests
download_manifest.csv
organize_manifest.csv

# Teaching materials
*.ppt
*.pptx
*.pps
*.ppsx
*.pdf

# Python cache and environments
__pycache__/
*.pyc
*.pyo
.venv/
venv/
env/

# Editor and operating-system files
.vscode/
.idea/
.DS_Store
Thumbs.db

Requirements

Python 3.10 or later

Playwright for Python

Chromium installed through Playwright

Install the required package:

python -m pip install --upgrade pip
python -m pip install playwright
python -m playwright install chromium

On systems where Playwright reports missing operating-system dependencies:

python -m playwright install --with-deps chromium

Windows Setup

The examples below use Windows Command Prompt.

Open Command Prompt and move to the project folder:

cd "C:\Users\YourName\Desktop\course_crawler"

Check that the scripts are present:

dir

Usage

1. Crawl One Course Website

First run:

py .\course_slides_crawler.py ^
  --start-url "https://moodle.example.ac.uk/course/view.php?id=12345" ^
  --output "%USERPROFILE%\Desktop\Master_Slides" ^
  --profile-dir "%LOCALAPPDATA%\course_crawler_profile" ^
  --login ^
  --max-depth 3 ^
  --max-pages 500 ^
  --delay 1.5

When the browser opens:

Complete the university login.

Wait until the course page is fully visible.

Return to Command Prompt.

Press Enter.

The files will be saved under:

C:\Users\YourName\Desktop\Master_Slides

The persistent browser profile will be stored under:

C:\Users\YourName\AppData\Local\course_crawler_profile

Do not upload or share this profile directory. It may contain active login data.

2. Run Again Without Manual Login

After a successful first login, the same profile may reuse the existing session:

py .\course_slides_crawler.py ^
  --start-url "https://moodle.example.ac.uk/course/view.php?id=12345" ^
  --output "%USERPROFILE%\Desktop\Master_Slides" ^
  --profile-dir "%LOCALAPPDATA%\course_crawler_profile" ^
  --max-depth 3 ^
  --max-pages 500 ^
  --delay 1.5

Add --login again if the session has expired.

3. Crawl Multiple Course Websites

Repeat --start-url:

py .\course_slides_crawler.py ^
  --start-url "https://moodle.example.ac.uk/course/view.php?id=12345" ^
  --start-url "https://moodle.example.ac.uk/course/view.php?id=67890" ^
  --output "%USERPROFILE%\Desktop\Master_Slides" ^
  --profile-dir "%LOCALAPPDATA%\course_crawler_profile" ^
  --login ^
  --max-depth 3 ^
  --max-pages 1000 ^
  --delay 1.5

4. Allow an Additional Domain

Some course pages link to SharePoint or another university-managed domain.

py .\course_slides_crawler.py ^
  --start-url "https://moodle.example.ac.uk/course/view.php?id=12345" ^
  --allow-domain "example.sharepoint.com" ^
  --output "%USERPROFILE%\Desktop\Master_Slides" ^
  --profile-dir "%LOCALAPPDATA%\course_crawler_profile" ^
  --login ^
  --max-depth 3 ^
  --max-pages 500

Use the exact trusted domain. Avoid broad domains unless necessary.

5. Organize All Downloaded Courses

After crawling has finished:

py .\organize_course_slides.py ^
  --input "%USERPROFILE%\Desktop\Master_Slides" ^
  --output "%USERPROFILE%\Desktop\Organized_Courses"

Example result:

Organized_Courses/
├── COMP0249/
├── COMP0123/
├── COMP0158/
└── organize_manifest.csv

By default, assessment-related files are excluded and the original downloaded files remain unchanged.

6. Organize One Course Only

py .\organize_course_slides.py ^
  --input "%USERPROFILE%\Desktop\Master_Slides" ^
  --output "%USERPROFILE%\Desktop\Organized_Courses" ^
  --course COMP0249

Repeat --course to select several modules:

py .\organize_course_slides.py ^
  --input "%USERPROFILE%\Desktop\Master_Slides" ^
  --output "%USERPROFILE%\Desktop\Organized_Courses" ^
  --course COMP0249 ^
  --course COMP0123

7. Organize by Week

py .\organize_course_slides.py ^
  --input "%USERPROFILE%\Desktop\Master_Slides" ^
  --output "%USERPROFILE%\Desktop\Organized_Courses" ^
  --by-week

Example:

Organized_Courses/
└── COMP0249/
    ├── Week_01/
    ├── Week_02/
    ├── Week_03/
    └── Other/

8. Keep Only PowerPoint Files

py .\organize_course_slides.py ^
  --input "%USERPROFILE%\Desktop\Master_Slides" ^
  --output "%USERPROFILE%\Desktop\Organized_Courses" ^
  --ppt-only

This excludes PDFs.

9. Include Assessment Files

Assessment-related files are excluded by default.

To include them:

py .\organize_course_slides.py ^
  --input "%USERPROFILE%\Desktop\Master_Slides" ^
  --output "%USERPROFILE%\Desktop\Organized_Courses" ^
  --include-assessment

Use this carefully. Assignment pages may contain personal or student-submitted files.

10. Move Instead of Copy

The organizer copies files by default.

To move them:

py .\organize_course_slides.py ^
  --input "%USERPROFILE%\Desktop\Master_Slides" ^
  --output "%USERPROFILE%\Desktop\Organized_Courses" ^
  --move

This changes the original download directory. Copying is safer for the first run.

Important Options

Crawler

Option

Purpose

--start-url

Starting course URL. Repeat for multiple courses.

--output

Download output directory.

--profile-dir

Persistent browser profile directory.

--login

Pause for manual login before crawling.

--headless

Run without a visible browser window.

--allow-domain

Allow recursive crawling of an additional trusted domain.

--follow-all-domains

Allow recursive crawling across all domains. Use cautiously.

--no-external-files

Do not inspect external files directly linked from course pages.

--max-depth

Maximum link depth from the starting page.

--max-pages

Maximum number of pages to visit.

--max-file-mb

Maximum file size in megabytes.

--timeout

Navigation and request timeout in seconds.

--delay

Delay between processed pages in seconds.

Organizer

Option

Purpose

--input

Crawler output directory containing download_manifest.csv.

--output

Destination directory for organized courses.

--course

Restrict organization to a selected course code.

--by-week

Create week-based subfolders.

--ppt-only

Exclude PDFs.

--include-assessment

Include assignments and other assessment files.

--extra-exclude

Add another exclusion keyword.

--include-unsorted

Put unidentified files in UNSORTED.

--prefix-source

Prefix filenames with the source-page title.

--move

Move files instead of copying them.

Crawl Depth

The crawler uses link depth rather than repeated crawl cycles:

Depth 0: the starting course page
Depth 1: pages linked directly from the course page
Depth 2: pages linked from depth-1 pages
Depth 3: pages linked from depth-2 pages

For most Moodle courses, the following is a practical starting point:

--max-depth 2

or:

--max-depth 3

Higher depths may cause the crawler to explore assessment pages, archived modules, late-summer assessment pages, and unrelated Moodle navigation.

Output Files

The crawler creates:

```text
Master_Slides/
│
├── download_manifest.csv
│
└── files/
    │
    ├── Course Page Title A/
    │
    ├── Course Page Title B/
    │
    └── ...
```

download_manifest.csv records:

saved filename;

relative saved path;

file size;

SHA-256 hash;

source-page title;

source-page URL;

requested download URL;

final URL;

content type;

HTTP status.

The organizer creates:

```text
Organized_Courses/
│
├── COMP0249/
│
├── COMP0123/
│
├── COMP0158/
│
└── organize_manifest.csv
```

Troubleshooting

WinError 123

This usually happens when PowerShell environment-variable syntax is used inside Command Prompt.

Use Command Prompt syntax:

%USERPROFILE%
%LOCALAPPDATA%

Do not use the following in Command Prompt:

$HOME
$env:LOCALAPPDATA

Chromium is not installed

Run:

py -m playwright install chromium

Login redirects keep repeating

Keep the browser window open.

Complete all Microsoft or university authentication steps.

Wait until the course page is fully visible.

Return to the terminal and press Enter.

The crawler visits too many Moodle pages

Reduce:

--max-depth
--max-pages

A safer configuration is:

--max-depth 2 --max-pages 300

No files are downloaded

Possible causes include:

login was not completed;

files are inside an iframe or another trusted domain;

the linked resource is not a supported file type;

the course platform generates downloads through a custom JavaScript action;

the additional domain was not added with --allow-domain;

the server blocked or interrupted the request.

Stop the crawler safely

Press:

Ctrl + C

Files that were already downloaded remain on disk.

Responsible Use

This software must not be used to:

bypass login systems or access controls;

access modules without authorization;

scrape private student information;

collect or publish student submissions;

overload a learning platform;

redistribute copyrighted course materials;

upload browser profiles, cookies, tokens, or authentication data.

Only the source code should be committed to a public repository.

Downloaded materials, manifests, and authentication profiles should remain local.

Security Notes

The browser profile directory may contain:

login cookies;

session tokens;

cached account information;

authenticated browsing state.

Treat it as sensitive data.

Do not:

commit it to Git;

upload it to cloud storage without protection;

send it to another person;

reuse an untrusted profile directory.

Limitations

Some download buttons are not ordinary links and may require site-specific handling.

The crawler does not guarantee complete coverage of every Moodle plugin.

Very deep crawls may reach unrelated pages.

Course-code detection assumes a pattern such as four letters followed by four digits.

Week detection depends on words such as Week or Lecture appearing in filenames or page titles.

Authentication may expire and require another manual login.

The crawler does not bypass permissions or protected resources.

License

Choose a license that matches how you want others to use the source code.

For a permissive open-source release, the MIT License is a common option. The license applies only to the source code in this repository. It does not grant rights to any course materials downloaded with the software.

Disclaimer

This project is provided for personal academic file management and authorized educational use.

The user is responsible for complying with:

university regulations;

course-platform terms;

copyright law;

data-protection requirements;

access-control policies.

The authors and contributors are not responsible for unauthorized use, redistribution of teaching materials, account restrictions, or service disruption caused by misuse.
