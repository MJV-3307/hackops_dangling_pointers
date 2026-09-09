from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from gridfs import GridFS
from dotenv import load_dotenv
import os
import tempfile
import ocrmypdf

load_dotenv()

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------
# MongoDB connection
# ---------------------------------------------------------

client = MongoClient(os.getenv("MONGO_URI"))

db = client[os.getenv("DATABASE_NAME", "BotPressTest")]

# ---------------------------------------------------------
# GridFS
# ---------------------------------------------------------
#
# All current OCR-processed PDFs are stored in this GridFS
# bucket.
#
fs = GridFS(db, collection="documents")


# ---------------------------------------------------------
# Home
# ---------------------------------------------------------

@app.route("/")
def home():
    return jsonify({
        "message": "Document upload server is running"
    })


# ---------------------------------------------------------
# Upload PDF
# ---------------------------------------------------------

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

        # -------------------------------------------------
        # Create temporary files
        # -------------------------------------------------
        #
        # input_pdf  = original uploaded PDF
        # output_pdf = OCR-processed PDF
        #
        # These are temporary and will be deleted after
        # processing.
        #

        with tempfile.TemporaryDirectory() as temp_dir:

            input_pdf = os.path.join(
                temp_dir,
                "input.pdf"
            )

            output_pdf = os.path.join(
                temp_dir,
                "ocr_output.pdf"
            )

            # ---------------------------------------------
            # Save uploaded PDF temporarily
            # ---------------------------------------------

            file.save(input_pdf)

            # ---------------------------------------------
            # Run OCR
            # ---------------------------------------------
            #
            # OCRmyPDF creates a searchable/OCR-enabled PDF.
            #
            # skip_text=True means:
            # If the PDF already contains selectable text,
            # OCRmyPDF will leave that text alone rather
            # than unnecessarily OCRing it.
            #

            ocrmypdf.ocr(
                input_pdf,
                output_pdf,
                skip_text=True
            )

            # ---------------------------------------------
            # Delete the existing document(s) from GridFS
            # ---------------------------------------------
            #
            # We are intentionally replacing the previous
            # document.
            #
            # Nothing is deleted until the OCR processing
            # succeeds.
            #

            existing_files = fs.find()

            for existing_file in existing_files:
                fs.delete(existing_file._id)

            # ---------------------------------------------
            # Store the new OCR PDF in GridFS
            # ---------------------------------------------

            with open(output_pdf, "rb") as processed_pdf:

                new_file_id = fs.put(
                    processed_pdf,
                    filename=file.filename,
                    content_type="application/pdf"
                )

            # ---------------------------------------------
            # Return success response
            # ---------------------------------------------

            return jsonify({
                "message": "PDF uploaded and converted to OCR successfully.",
                "fileId": str(new_file_id),
                "fileName": file.filename
            }), 201

    except ocrmypdf.exceptions.MissingDependencyError as e:

        print("OCR dependency error:", e)

        return jsonify({
            "message": "OCR processing dependencies are missing.",
            "error": str(e)
        }), 500

    except Exception as e:

        print("Upload/OCR error:", e)

        return jsonify({
            "message": "Failed to process PDF.",
            "error": str(e)
        }), 500


# ---------------------------------------------------------
# Get current document
# ---------------------------------------------------------

@app.route("/api/documents/current", methods=["GET"])
def get_current_document():

    try:

        # Get all files currently stored in the documents
        # GridFS bucket.

        files = list(fs.find())

        # No document available

        if not files:
            return jsonify({
                "message": "No document is currently stored.",
                "document": None
            }), 404

        # Since our upload process deletes the old document
        # before storing the new one, there should normally
        # only be one file.
        #
        # We use the newest file if more than one somehow
        # exists.

        current_file = max(
            files,
            key=lambda x: x.upload_date
        )

        return jsonify({
            "message": "Current document retrieved successfully.",
            "document": {
                "fileId": str(current_file._id),
                "fileName": current_file.filename,
                "contentType": current_file.content_type,
                "uploadDate": current_file.upload_date.isoformat()
            }
        }), 200

    except Exception as e:

        print("Error retrieving current document:", e)

        return jsonify({
            "message": "Failed to retrieve current document."
        }), 500


# ---------------------------------------------------------
# Run Flask server
# ---------------------------------------------------------

if __name__ == "__main__":
    app.run(
        port=5000,
        debug=True
    )