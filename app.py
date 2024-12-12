import os
from flask import Flask, render_template, request, jsonify ,redirect, url_for
import openpyxl
from habanero import Crossref
import bibtexparser
import requests
from bs4 import BeautifulSoup
import time
import json
from flask import Flask, request, render_template, redirect, url_for
from flask import Flask, render_template, request, redirect, url_for, flash
import pyrebase
from google.cloud import firestore
import json
import re


os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "C:\\Users\\Ingle\\OneDrive\\Attachments\\Desktop\\PublicationSummerizer\\bugbyte_backend\\firebase_key.json"

app = Flask(__name__)
app.secret_key = "a9b8c7d6e5f4a3b2c1d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5"

firebase_config = {
  "apiKey": "AIzaSyDn7N-WIV_N4rn7VWcmPZQrbLumm9-t4OI",
  "authDomain": "publicationsummarizer.firebaseapp.com",
  "databaseURL": "https://publicationsummarizer-default-rtdb.asia-southeast1.firebasedatabase.app",
  "projectId": "publicationsummarizer",
  'storageBucket': "publicationsummarizer.firebasestorage.app",
  "messagingSenderId": "552696279504",
  "appId": "1:552696279504:web:a3cfb0cbf3226f084c89d5",
  "measurementId": "G-RVQ51GGTRK"
}

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

firebase = pyrebase.initialize_app(firebase_config)
auth = firebase.auth()
db = firebase.database()

# Email and password validations
def is_valid_email(email):
    email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(email_regex, email)

def is_valid_password(password):
    return len(password) >= 6



# Persistent storage for results
original_publications = {}
filtered_publications = {}
filters = {"year_from": None, "year_to": None, "type": None}

@app.route('/excel', methods=['GET', 'POST'])
def index():
    global original_publications, filtered_publications, filters
    unique_types = []
    years = []

    if request.method == 'POST':
        # Handle file upload
        if 'excel_file' in request.files:
            excel_file = request.files['excel_file']

            if excel_file.filename.endswith('.xlsx'):
                file_path = os.path.join(UPLOAD_FOLDER, excel_file.filename)
                excel_file.save(file_path)

                # Read Excel and fetch data
                try:
                    paper_data = read_excel(file_path)
                    publications = {}

                    for author, fields in paper_data.items():
                        if author != "N/A" and author:
                            publications[author] = fetch_crossref_papers(author)

                    original_publications.update(publications)
                    filtered_publications = original_publications.copy()

                    # Prepare filter options
                    for author, papers in original_publications.items():
                        for paper in papers:
                            if paper.get("type"):
                                unique_types.append(paper["type"])
                            if paper.get("year"):
                                years.append(paper["year"])

                    unique_types = sorted(set(unique_types))
                    years = sorted(set(years))
                except Exception as e:
                    return f"Error processing file: {e}", 500

        # Handle filtering
        elif 'filter' in request.form:
            filters["year_from"] = request.form.get("year_from", type=int)
            filters["year_to"] = request.form.get("year_to", type=int)
            filters["type"] = request.form.get("type")

            # Apply filters starting from the original results
            filtered_publications = apply_filters(original_publications, filters)

    return render_template(
        'index.html',
        publications=filtered_publications,
        filters=filters,
        authors=sorted(original_publications.keys()),
        unique_types=unique_types,
        years=years
    )

@app.route('/author/<author_name>', methods=['GET'])
def get_author_publications(author_name):
    global original_publications, filtered_publications, filters

    # Retrieve results for a single author after applying filters
    author_papers = filtered_publications.get(author_name, [])
    return jsonify(author_papers)

# Function to read Excel file
def read_excel(file_path):
    paper_data = {}
    workbook = openpyxl.load_workbook(file_path)
    sheet = workbook.active

    for row in sheet.iter_rows(min_row=2, values_only=True):  # Skip header row
        name = row[0] or "N/A"
        paper_data[name] = {
            "publication": row[1] or "N/A",
            "paper_type": row[2] or "N/A",
            "pub_year": row[3] or "N/A",
            "important_field": row[4] or "N/A",
        }
    return paper_data

# Function to fetch publications from CrossRef
def fetch_crossref_papers(author):
    cr = Crossref()
    try:
        works = cr.works(query=author, limit=5)
        paper_details = [
            {
                "title": item.get("title", ["N/A"])[0],
                "type": item.get("type", "N/A"),
                "year": item.get("published-print", {}).get("date-parts", [[None]])[0][0]
                or item.get("published-online", {}).get("date-parts", [[None]])[0][0],
                "authors": ", ".join(
                    f"{auth.get('given', '')} {auth.get('family', '')}".strip()
                    for auth in item.get("author", [])
                ),
            }
            for item in works.get("message", {}).get("items", [])
        ]
        return sorted(
            paper_details, key=lambda x: x.get("year", float("-inf")) or float("-inf"), reverse=True
        )
    except Exception as e:
        return [{"error": str(e)}]


#working good 
def apply_filters(publications, filters):
    year_from = filters["year_from"]
    year_to = filters["year_to"]
    paper_type = filters["type"]

    filtered = {}
    for author, papers in publications.items():
        filtered_papers = [
            paper
            for paper in papers
            if (year_from is None or (paper["year"] and paper["year"] >= year_from))
            and (year_to is None or (paper["year"] and paper["year"] <= year_to))
            and (not paper_type or paper["type"].lower() == paper_type.lower())
        ]
        if filtered_papers:
            filtered[author] = filtered_papers

    return filtered

def fetch_author_url(name):
    # Replace spaces with '+' for URL encoding
    url = f'https://dblp.org/search/author/api?q={name.replace(" ", "+")}&format=json'
    response = requests.get(url)
    
    if response.status_code != 200:
        return None  # Handle API failure
    try:
        data = response.json()
        # Check if there are hits
        if data['result']['hits']['hit']:
            # Return the URL of the first author found
            return data['result']['hits']['hit'][0]['info']['url']
    except (KeyError, IndexError):
        return None  # Handle cases where the expected data structure doesn't exist
    return None

def fetch_papers(author_url):
    response = requests.get(author_url)
    if response.status_code != 200:
        return []  # If the request fails, return an empty list
    
    soup = BeautifulSoup(response.text, 'html.parser')
    papers = []
    seen = set()  # Set to track unique papers by title or other criteria

    results = soup.find_all('li', class_='entry')

    for result in results:
        title_tag = result.find('span', class_='title')
        title = title_tag.text.strip() if title_tag else "No Title"
        
        # Check if the title is already seen
        if title in seen:
            continue  # Skip duplicate entries
        seen.add(title)

        author_tags = result.find_all('span', itemprop='author')
        authors = [author.text.strip() for author in author_tags]
        formatted_authors = ', '.join(authors) if authors else "No Author Info"
        
        snippet_tag = result.find('span', class_='abstract')
        snippet = snippet_tag.text.strip() if snippet_tag else "No Abstract"
        snippet = snippet.replace("△ Less", "").strip()
        
        year_tag = result.find('span', itemprop='datePublished')
        year = year_tag.text.strip() if year_tag else "No Year"
        
        link_tag = result.find('div', class_='head').find('a')
        link = link_tag['href'] if link_tag else "No Link"
        
        type_ = result.find('img').get('title', 'No Type')

        papers.append({
            "Title": title,
            "Authors": formatted_authors,
            "Year": year,
            "Link": link,
            "Type": type_,
            "Description": snippet,
        })
    
    # Save papers to text.json
    with open('text.json', 'w', encoding='utf-8') as w:
        json.dump(papers, w, ensure_ascii=False, indent=4)
    
    return papers



@app.route('/bibtex')
def bibtex():
    return render_template('bibtex.html')

@app.route('/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return redirect(url_for('bibtex'))

    file = request.files['file']

    if file.filename == '':
        return redirect(url_for('bibtex'))

    faculty_publications = {}
    authors_set = set()  # Use a set to ensure uniqueness of authors

    if file and file.filename.endswith('.bib'):
        bib_data = file.read().decode('utf-8')
        bib_database = bibtexparser.loads(bib_data)
        entries = bib_database.entries

        # Extract authors from BibTeX entries and store them in authors_set
        for entry in entries:
            faculty_name = entry.get('author')
            if faculty_name:
                # Split authors if multiple authors are present
                author_list = faculty_name.split(' and ')
                for author in author_list:
                    # Clean up and add to set
                    cleaned_author = author.strip()
                    if cleaned_author:
                        authors_set.add(cleaned_author)

        # Convert set to a list to pass to the template
        authors_list = list(authors_set)

        return render_template('bibtex.html', entries=entries, faculty_publications=faculty_publications, authors=authors_list)

    return redirect(url_for('bibtex'))


@app.route("/")
def landing():
    return render_template("landing.html")


@app.route('/search', methods=['POST'])
def search():
    author_name = request.form.get('author')
    if not author_name:
        return redirect(url_for('bibtex'))
    
    start = time.time()
    
    # Fetch author URL and papers based on the author name
    author_url = fetch_author_url(author_name)
    
    if author_url:
        publications = fetch_papers(author_url)
    else:
        publications = []  # If no author URL is found, return an empty list

    end = time.time()
    print(f'Time taken: {end - start} seconds')
    
    return render_template('bibtex.html', faculty_publications={author_name: publications})


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'GET':
        return render_template('signup.html')

    email = request.form.get('email')
    password = request.form.get('password')
    user_type = request.form.get('logged_in_as', 'user')  # Default to 'user' if not provided

    if not email or not is_valid_email(email):
        flash("Invalid email address.")
        return redirect(url_for('signup'))

    if not password or not is_valid_password(password):
        flash("Password must be at least 6 characters long.")
        return redirect(url_for('signup'))

    try:
        # Create user with Firebase Authentication
        user = auth.create_user_with_email_and_password(email, password)
        auth.send_email_verification(user['idToken'])

        flash("Signup successful! A verification email has been sent.")

        # Redirect to respective dashboard based on user type
        if user_type == 'user':
            return redirect(url_for('user_dashboard_page'))  # Redirect to user dashboard
        elif user_type == 'organization':
            return redirect(url_for('organization_dashboard_page'))  # Redirect to organization dashboard
        else:
            flash("Invalid user type selected.")
            return redirect(url_for('signup'))  # Redirect back to signup if invalid user type

    except Exception as e:
        error_message = str(e)
        flash(f"Error: {error_message}")
        return redirect(url_for('signup'))

    
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    email = request.form.get('email')
    password = request.form.get('password')

    if not email or not is_valid_email(email):
        flash("Invalid email address.")
        return redirect(url_for('login'))

    if not password:
        flash("Password is required.")
        return redirect(url_for('login'))

    try:
        # Authenticate user with Firebase Authentication
        user = auth.sign_in_with_email_and_password(email, password)

        # Check if the email is verified
        if not user['emailVerified']:
            flash("Email is not verified. Please check your inbox for a verification link.")
            return redirect(url_for('login'))

        flash("Login successful!")

        # Redirect to respective dashboard based on user type
        # Assume `user_type` is stored in Firestore for each user (you can query this to fetch user_type)
        doc_ref = firestore.collection("users").document(email)  # Or use your correct collection
        user_data = doc_ref.get()

        if user_data.exists:
            user_type = user_data.to_dict().get('user_type')
            if user_type == 'user':
                return redirect(url_for('user_dashboard'))  # Redirect to user dashboard
            elif user_type == 'organization':
                return redirect(url_for('organization_dashboard'))  # Redirect to organization dashboard
            else:
                flash("Invalid user type.")
                return redirect(url_for('login'))  # Redirect back to login if invalid user type
        else:
            flash("User not found.")
            return redirect(url_for('login'))

    except Exception as e:
        error_message = str(e)
        flash(f"Error: {error_message}")
        return redirect(url_for('login'))

@app.route('/user/<string:email>')
def user_dashboard(email):
    # Store email in local storage and render user dashboard
    js = f"localStorage.setItem('userEmail', '{email}');"
    html = f"<script>{js}</script>"
    html += "<script>console.log('User Email:', localStorage.getItem('userEmail'));</script>"
    html += render_template('user.html', email=email)
    return html

@app.route('/organization/<string:email>')
def organization_dashboard(email):
    # Store email in local storage and render organization dashboard
    js = f"localStorage.setItem('userEmail', '{email}');"
    html = f"<script>{js}</script>"
    html += "<script>console.log('User Email:', localStorage.getItem('userEmail'));</script>"
    html += render_template('org.html', email=email)
    return html


# ... (rest of your routes and app logic)
@app.route('/dashboard/user')
def user_dashboard_page():
    email = request.args.get('email', '')
    return render_template('user_dashboard.html', email=email)

@app.route('/dashboard/organization')
def organization_dashboard_page():
    email = request.args.get('email', '')
    return render_template('organization_dashboard.html', email=email)


@app.route("/pricing")
def pricing():
    return render_template("pricing.html") 

@app.route("/landing1")
def landing1():
    return render_template("landing1.html") 

if __name__ == '__main__':
    app.run(debug=True)



# working 