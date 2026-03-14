# Health AI Web Application

A Flask-based healthcare emergency web application with:
- Symptom-based disease prediction
- AI-powered report analysis (PDF/text)
- MedlinePlus integration for health education
- Patient report upload, analyze, download, and delete
- Authentication, dashboards, hospital map, SOS and emergency features

## Project Structure

```
backend/
  app.py
  report_analyzer.py
  uploads/
frontend/
  index.html
  dashboard.html
  login.html
  signup.html
  patient-reports.html
  script.js
  style.css
data/
  patient_reports.json
  users.json
  ...
model/
  train_model.py
```

## Features

### Backend
- Flask API for user auth, prediction, report upload/analyze/delete
- PDF and text medical report parsing via pdfplumber
- Medical value extraction (hemoglobin, blood sugar, blood pressure, cholesterol, etc.)
- Disease and abnormality detection + risk level
- MedlinePlus Connect API integration for disease educational info
- Save and load patient report metadata in JSON

### Frontend
- Symptom checker with prediction and risk output
- Medical report upload and analysis UI
- Report management (list, view, analyze, download, delete)
- Simple dashboard with health assistant and emergency features

## Quick Setup

1. Clone repository:
```bash
git clone <repo-url>
cd health_AI_web
```

2. Create Python venv and activate:
```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

3. Install requirements:
```bash
pip install -r requirements.txt
pip install requests
```

4. Run backend:
```bash
cd backend
python app.py
```

5. Open frontend in browser:
```
http://127.0.0.1:5500/frontend/index.html
```

## API Endpoints

- `POST /signup` - Register user
- `POST /login` - Login
- `GET /symptoms` - Get symptom list
- `POST /extract-symptoms` - Extract symptoms from text + MedlinePlus info
- `POST /predict` - Predict disease + MedlinePlus info
- `POST /upload-report` - Upload medical report
- `POST /analyze-report` - Analyze existing or uploaded report
- `DELETE /delete-report/<id>` - Delete report
- `GET /patient-reports?user_id=<id>` - List user reports
- `GET /download-report/<id>` - Download uploaded report

## MedlinePlus Integration

The app fetches disease educational content from MedlinePlus Connect API and returns:
- `title`
- `summary`
- `source_url`
- `related_topics`

## Tips

- Use Firefox/Chrome devtools to inspect API responses and console logs.
- If CORS errors happen, restart backend and ensure correct headers.

## Notes

This project is for demo and educational use. It is not a medical diagnosis tool. Always consult a qualified healthcare professional.
