from flask import Flask, render_template, request, redirect,jsonify, flash, session, url_for, Response
from detect_bubbles import detect_bubbles
from process_bubble import process_bubble
from translator.translator import MangaTranslator
from add_text import add_text
from manga_ocr import MangaOcr
from PIL import Image
import numpy as np
import base64
import cv2
import os
import time
from flask_bcrypt import Bcrypt
from flask_session import Session
from pymongo import MongoClient
from datetime import datetime
from bson.objectid import ObjectId
from werkzeug.utils import secure_filename
from functools import wraps
from bson.binary import Binary
from bson.objectid import ObjectId

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "secret_key")
# Set the upload folder (ensure the folder exists)
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static/uploads')
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])

client = MongoClient("mongodb+srv://pkvinh22:5n1AJXI44co0ZQ4c@cluster0.qogo6.mongodb.net/")
db = client.flask_app
users_collection = db.users


app.config["SESSION_TYPE"] = "filesystem"
Session(app)
bcrypt = Bcrypt(app)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
MODEL_PATH = "model/model.pt"
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def home():
    if "username" not in session:
        return redirect(url_for("login"))
    return render_template("index.html", username=session["username"])


@app.context_processor
def utility_processor():
    def get_user():
        if 'user_id' in session:
            # Use ObjectId for accurate querying
            user = users_collection.find_one({"_id": ObjectId(session.get("user_id"))})
            print("DEBUG - Retrieved user:", user)  # For debugging
            return user
        return None
    
    return {'get_user': get_user}

@app.route("/get_profile_image/<username>")
def get_profile_image(username):
    user = users_collection.find_one({"username": username})
    if user and user.get("profile_picture"):
        # You can set the mimetype based on the file type.
        # Here, we assume the image is in PNG format.
        return Response(user["profile_picture"], mimetype="image/png")
    else:
        # If no profile picture is found, redirect to a default image
        return redirect(url_for('static', filename='img/default_profile.png'))

@app.route("/login", methods=["GET", "POST"])

def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        remember = request.form.get("remember")

        user = users_collection.find_one({"username": username})
        
        if not user:
            flash("User not found, please create a new account", "danger")
        elif not bcrypt.check_password_hash(user["password"], password):
            flash("Wrong username or password", "danger")
        else:
            session["username"] = username
            session["user_id"] = str(user["_id"])  # Store user ID in session
            session["user_data"] = {
            "username": user["username"],
            "email": user["email"],
            "profile_picture": user["profile_picture"]
            }
            if remember:
                session["remember_me"] = True
            else:
                session.pop("remember_me", None)
            return redirect(url_for("home"))

    remembered_user = session.get("remember_me") and session.get("username")
    return render_template("login.html", remembered_user=remembered_user)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Get form data
        username = request.form["username"]
        password = request.form["password"]
        confirm_password = request.form["confirm_password"]
        full_name = request.form["full_name"]
        email = request.form["email"]
        age = request.form.get("age", "")  # Use get method to handle optional fields
        
        # Validate form data
        if not username or not password or not full_name or not email:
            flash("Required fields cannot be empty", "danger")
            return render_template("register.html")
        elif password != confirm_password:
            flash("Passwords do not match", "danger")
            return render_template("register.html")
        elif users_collection.find_one({"username": username}):
            flash("Username already exists", "danger")
            return render_template("register.html")
        elif users_collection.find_one({"email": email}):
            flash("Email already registered", "danger")
            return render_template("register.html")
        
        # Process profile picture if uploaded
        profile_pic = "default_profile.png"  # Default profile picture
        if 'profile_picture' in request.files:
            file = request.files['profile_picture']
            if file and file.filename != '' and allowed_file(file.filename):
                profile_pic = Binary(file.read())
        
        # Hash password
        hashed_pw = bcrypt.generate_password_hash(password).decode("utf-8")
        
        # Create user document
        new_user = {
            "username": username,
            "password": hashed_pw,
            "full_name": full_name,
            "email": email,
            "age": age,
            "profile_picture": profile_pic,
            "gallery": [],  # Empty gallery to start
            "created_at": datetime.now()
        }
        
        # Insert into database
        users_collection.insert_one(new_user)
        flash("Account created successfully!", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/translate", methods=["POST"])
def upload_file(): 
    if "Opus-mt model" == request.form["selected_translator"]: 
        selected_translator = "hf" 
    elif "DeepL (Reccommend)" == request.form["selected_translator"]: 
        selected_translator = "deepl" 
    else: 
        selected_translator = request.form["selected_translator"].lower() 
     
    # Handle font name processing
    selected_font = request.form["selected_font"]
    if selected_font != "Felt Regular":
        selected_font = selected_font.lower()
    
    if "file" in request.files: 
        file = request.files["file"] 
        name = file.filename.split(".")[0] 
 
        file_stream = file.stream 
        file_bytes = np.frombuffer(file_stream.read(), dtype=np.uint8) 
        image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR) 
 
        results = detect_bubbles(MODEL_PATH, image) 
 
        manga_translator = MangaTranslator() 
        mocr = MangaOcr() 
        bubble_texts = [] 
        for i, result in enumerate(results, 1): 
            x1, y1, x2, y2, score, class_id = result 
 
            detected_image = image[int(y1):int(y2), int(x1):int(x2)] 
 
            im = Image.fromarray(np.uint8(detected_image * 255)) 
            text = mocr(im) 
 
            detected_image, cont = process_bubble(detected_image) 
            text_translated = manga_translator.translate(text, method=selected_translator) 
            time.sleep(1) 
            
            # Determine correct font path
            font_path = f"fonts/{selected_font}i.ttf" if selected_font != "Felt Regular" else "fonts/Felt Regular.ttf"
            
            add_text(detected_image, text_translated, font_path, cont) 
            bubble_texts.append({"index": i, "x1": x1, "y1": y1, "x2": x2, "y2": y2, "text": text_translated}) 
 
        _, buffer = cv2.imencode(".png", image) 
        image = buffer.tobytes() 
        encoded_image = base64.b64encode(image).decode("utf-8") 
 
        return render_template("translate.html", name=name, uploaded_image=encoded_image, bubble_texts=bubble_texts) 
 
    return redirect("/")

def base64_to_cv2(image_base64):
    """ Convert Base64 Image to OpenCV Image """
    image_bytes = base64.b64decode(image_base64)  # Decode Base64 to bytes
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)  # Convert to numpy array
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)  # Decode as OpenCV image
    return image

def add_to_gallery():
    if "user_id" not in session:
        flash("Please login to add photos", "danger")
        return redirect(url_for("login"))
    
    if 'photo' not in request.files:
        flash("No photo part", "danger")
        return redirect(url_for("profile"))
    
    file = request.files['photo']
    if file.filename == '':
        flash("No photo selected", "danger")
        return redirect(url_for("profile"))
    
    if file and allowed_file(file.filename):
        # Create secure filename with username and timestamp to avoid collisions
        user = users_collection.find_one({"_id": ObjectId(session["user_id"])})
        filename = secure_filename(f"{user['username']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Add photo to user's gallery
        users_collection.update_one(
            {"_id": ObjectId(session["user_id"])},
            {"$push": {"gallery": {
                "filename": filename,
                "uploaded_at": datetime.now(),
                "description": request.form.get("description", "")
            }}}
        )
        flash("Photo added to gallery!", "success")
    else:
        flash("File type not allowed", "danger")
    
    return redirect(url_for("profile"))


@app.route("/update_bubbles", methods=["POST"])
def update_bubbles():
    data = request.json
    image_data = data.get("image_data")  # Base64 image data
    default_font = data.get("font", "animeace")  # Default font
    bubbles = data.get("bubble_texts", [])  # List of all text bubbles
    
    if not image_data or not bubbles:
        return jsonify({"error": "Missing image or bubbles data"}), 400

    # Decode Base64 to OpenCV Image
    try:
        image_bytes = base64.b64decode(image_data)
        image_array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    except Exception as e:
        return jsonify({"error": f"Failed to decode image: {str(e)}"}), 400

    # Apply text updates to all bubbles
    for bubble in bubbles:
        # Get index and text
        index = int(bubble["index"])
        new_text = bubble["text"]

        # Get style settings
        font_name = bubble.get("font", default_font).lower()
        font_size = bubble.get("size", "Medium").lower()
        is_bold = bubble.get("bold", False)
        is_italic = bubble.get("italic", False)
        
        # Determine the font path based on style options
        font_style = ""
        if is_bold and is_italic:
            font_style = "bi"  # Bold and italic
        elif is_bold:
            font_style = "b"   # Bold only
        elif is_italic:
            font_style = "i"   # Italic only
        
        # Construct font path
        font_path = f"fonts/{font_name}{font_style}.ttf"
        
        # Convert size to numerical scaling factor
        size_scale = 1.0  # Default for medium
        if font_size == "small":
            size_scale = 0.8
        elif font_size == "large":
            size_scale = 1.2

        # Extract bubble region
        x1, y1, x2, y2 = map(lambda v: round(float(v)), (bubble["x1"], bubble["y1"], bubble["x2"], bubble["y2"]))

        # Process the bubble
        cleaned_bubble, bubble_contour = process_bubble(image[y1:y2, x1:x2])

        # Apply new text with style settings
        updated_bubble = add_text(cleaned_bubble, new_text, font_path, bubble_contour, size_scale)

        # Replace the bubble in the main image
        image[y1:y2, x1:x2] = updated_bubble

    # Encode image back to Base64
    _, buffer = cv2.imencode(".png", image)
    new_base64_image = base64.b64encode(buffer).decode("utf-8")

    return jsonify({"updated_image": new_base64_image})

@app.route('/logout')
def logout():
    session.clear()  # Clear user session
    return redirect(url_for('login'))  # Redirect to login page

@app.route('/new_bubble', methods=['POST'])
def new_bubble():
    data = request.json
    image_data = data.get("image_data")
    bubble = data.get("bubble")
    selected_font = data.get("font", "Animeace")
    selected_translator = data.get("translator", "Bing")
    manga_translator = MangaTranslator()
    
    if not image_data or not bubble:
        return jsonify({"error": "Missing image data or bubble coordinates"}), 400
    
    # Convert base64 to image
    image = np.frombuffer(base64.b64decode(image_data), dtype=np.uint8)
    image = cv2.imdecode(image, cv2.IMREAD_COLOR)
    
    # Extract bubble region
    x1, y1, x2, y2 = map(lambda v: round(float(v)), (bubble["x1"], bubble["y1"], bubble["x2"], bubble["y2"]))
    detected_image = image[y1:y2, x1:x2]
    
    # Perform OCR
    mocr = MangaOcr()
    im = Image.fromarray(np.uint8(detected_image))
    text = mocr(im)
    
    # Process detected bubble and translate
    detected_image, cont = process_bubble(detected_image)
    text_translated = manga_translator.translate(text, method=selected_translator)
    
    # Determine correct font path
    font_path = f"fonts/{selected_font}i.ttf" if selected_font != "Felt Regular" else "fonts/Felt Regular.ttf"
    
    # Render translated text on the bubble
    add_text(detected_image, text_translated, font_path, cont)
    
    # Convert updated image back to base64
    _, updated_image = cv2.imencode('.png', image)
    updated_image_base64 = base64.b64encode(updated_image).decode('utf-8')
    
    # Add new bubble to the list
    new_bubble = {
        "index": len(data.get("bubble_texts", [])),
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2,
        "text": text_translated
    }
    data["bubble_texts"].append(new_bubble)
    
    return jsonify({
        "updated_image": updated_image_base64,
        "bubble_texts": data["bubble_texts"]
    })

@app.route("/save_image", methods=["POST"])
def save_image():
    if "user_id" not in session:
        return jsonify({"error": "User not logged in"}), 401
    
    data = request.json
    image_data = data.get("image")

    try:
        user_id = ObjectId(session.get("user_id"))
    except Exception as e:
        return jsonify({"error": "Invalid user ID"}), 400

    if not image_data:
        return jsonify({"error": "No image provided"}), 400

    # Create a new image object with a unique ID
    image_object = {
        "_id": ObjectId(),  # img_id
        "data": image_data
    }

    # Store the image object in the user's gallery
    users_collection.update_one(
        {"_id": user_id},
        {"$push": {"gallery": image_object}}
    )

    return jsonify({
        "message": "Image saved successfully!",
        "img_id": str(image_object["_id"])
    })

@app.route("/gallery")
def gallery():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    user = users_collection.find_one({"_id": ObjectId(user_id)})

    # Each item in gallery is a dict: { "_id": ..., "data": ... }
    gallery_items = user.get("gallery", [])

    # Pass full items (id and data) to the template
    return render_template("gallery.html", user_gallery=gallery_items)

@app.route("/delete_image", methods=["POST"])
def delete_image():
    if "user_id" not in session:
        return redirect("/login")

    user_id = session["user_id"]
    img_id = request.form.get("img_id")

    if not img_id:
        return "Image ID not provided", 400

    try:
        users_collection.update_one(
            {"_id": ObjectId(user_id)},
            {"$pull": {"gallery": {"_id": ObjectId(img_id)}}}  
        )
    except Exception as e:
        return f"Error deleting image: {str(e)}", 500

    return redirect("/gallery")

@app.route('/profile')
def profile():
    if "user_id" not in session:
        return redirect("/login")

    if "user_data" in session:
        user = session["user_data"]
    else:
        # Fallback: fetch from database if session is missing (rare)
        user_id = session["user_id"]
        user_data = users_collection.find_one(
            {"_id": ObjectId(user_id)},
            {"username": 1, "email": 1, "profile_picture": 1, "gallery": 1}
        )
        user = dict(user_data)
        session["user_data"] = user  # Update session
    
    # Handle profile picture
    profile_pic = user.get("profile_picture")
    if profile_pic and profile_pic != "default_profile.png":
        if isinstance(profile_pic, bytes):
            base64_data = base64.b64encode(profile_pic).decode('utf-8')
            user["profile_picture_url"] = f"data:image/jpeg;base64,{base64_data}"
        else:
            user["profile_picture_url"] = url_for('static', filename='uploads/' + profile_pic)
    else:
        user["profile_picture_url"] = url_for('static', filename='images/default_profile.png')

    return render_template("profile.html", user=user)




if __name__ == "__main__":
    app.run(debug=True)
