from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from gridfs import GridFS
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
CORS(app)

# MongoDB connection
client = MongoClient(os.getenv("MONGO_URI"))

db = client[os.getenv("DATABASE_NAME", "BotPressTest")]

# GridFS
# All uploaded PDFs will remain stored here.
fs = GridFS(db, collection="documents")

# Collection used to keep track of which document is currently
# being used by Botpress.
document_metadata = db["document_metadata"]


@app.route("/")
def home():
    return jsonify({
        "message": "Document upload server is running"
    })


@app.route("/api/documents/upload", methods=["POST"])
def upload_document():

    # Check whether a file was sent
    if "document" not in request.files:
        return jsonify({
            "message": "No document was provided."
        }), 400

    file = request.files["document"]

    # Check filename
    if file.filename == "":
        return jsonify({
            "message": "No file selected."
        }), 400

    # Check PDF
    if file.content_type != "application/pdf":
        return jsonify({
            "message": "Only PDF files are allowed."
        }), 400

    try:
        # ---------------------------------------------------------
        # 1. Store the PDF in GridFS
        # ---------------------------------------------------------
        #
        # The PDF is NOT replacing or deleting any existing PDF.
        # Every uploaded PDF gets its own GridFS file.
        #
        file_id = fs.put(
            file,
            filename=file.filename,
            content_type="application/pdf"
        )

        # ---------------------------------------------------------
        # 2. Mark this PDF as the CURRENT document
        # ---------------------------------------------------------
        #
        # There will only be one document with:
        #     type = "current_document"
        #
        # When a new PDF is uploaded, this record is updated to
        # point to the new GridFS file.
        #
        document_metadata.update_one(
            {"type": "current_document"},
            {
                "$set": {
                    "fileId": str(file_id),
                    "fileName": file.filename,
                    "contentType": "application/pdf"
                }
            },
            upsert=True
        )

        # ---------------------------------------------------------
        # 3. Return the information to React
        # ---------------------------------------------------------

        return jsonify({
            "message": "PDF uploaded successfully.",
            "fileId": str(file_id),
            "fileName": file.filename,
            "current": True
        }), 201

    except Exception as e:
        print("Upload error:", e)

        return jsonify({
            "message": "Failed to upload PDF."
        }), 500


@app.route("/api/documents/current", methods=["GET"])
def get_current_document():

    try:
        # Find the document currently being used by Botpress
        current_document = document_metadata.find_one(
            {"type": "current_document"},
            {"_id": 0}
        )

        # No document has been uploaded yet
        if not current_document:
            return jsonify({
                "message": "No document has been uploaded yet.",
                "document": None
            }), 404

        return jsonify({
            "message": "Current document retrieved successfully.",
            "document": current_document
        }), 200

    except Exception as e:
        print("Error retrieving current document:", e)

        return jsonify({
            "message": "Failed to retrieve current document."
        }), 500


if __name__ == "__main__":
    app.run(port=5000, debug=True)