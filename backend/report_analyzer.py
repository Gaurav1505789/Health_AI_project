"""
Medical Report Analyzer Module

This module provides functionality to analyze medical reports (PDF or text files)
and extract important medical information such as:
- Patient demographics (name, age)
- Vital measurements (blood pressure, blood sugar, hemoglobin, cholesterol)
- Detected conditions and diagnoses
- Critical value alerts

The analyzer uses pattern matching to extract medical data and determine risk levels
based on normal/abnormal thresholds.
"""

import re
import json
from pathlib import Path
from typing import Dict, Tuple, Optional, List

try:
    import pdfplumber
except ImportError:
    pdfplumber = None


class MedicalReportAnalyzer:
    """
    Analyzes medical reports to extract and identify important medical information.
    """
    
    # Define regex patterns for extracting common medical values
    PATTERNS = {
        "patient_name": [
            r"(?:Name|Patient Name|Name of Patient)\s*[:=]?\s*([A-Za-z\s\.]+?)(?=\n|,|Age)",
            r"^([A-Z][a-z]+\s+[A-Z][a-z]+)(?:\s+[A-Z][a-z]+)?$",  # Title case names
        ],
        "age": [
            r"(?:Age|DOB|Date of Birth)\s*[:=]?\s*(\d{1,3})\s*(?:years|yrs|y\.o)",
            r"Age\s*[:=]?\s*(\d{1,3})",
        ],
        "blood_pressure": [
            r"(?:BP|Blood Pressure)\s*[:=]?\s*(\d{2,3})\s*[/x]\s*(\d{2,3})",
            r"(\d{2,3})\s*[/x]\s*(\d{2,3})\s*(?:mmhg|mm hg)",
        ],
        "blood_sugar": [
            r"(?:Fasting Blood Sugar|FBS|Blood Sugar|Glucose)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mg/dl|mg\/dl|fasting)",
            r"Glucose\s*[:=]?\s*(\d+(?:\.\d+)?)",
        ],
        "hemoglobin": [
            r"(?:Hemoglobin|HB|Hgb)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:g/dl|g\/dl|gm%)",
            r"(?:RBC|Hemoglobin)\s*[:=]?\s*(\d+(?:\.\d+)?)",
        ],
        "cholesterol": [
            r"(?:Total Cholesterol|Cholesterol)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mg/dl|mg\/dl)",
            r"Cholesterol\s*[:=]?\s*(\d+(?:\.\d+)?)",
        ],
        "triglycerides": [
            r"(?:Triglycerides|TG)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mg/dl|mg\/dl)",
        ],
        "sodium": [
            r"(?:Sodium|Na)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:meq/l|mEq/L)",
        ],
        "potassium": [
            r"(?:Potassium|K)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:meq/l|mEq/L)",
        ],
        "creatinine": [
            r"(?:Creatinine|Cr)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mg/dl|mg\/dl)",
        ],
        "bilirubin": [
            r"(?:Total Bilirubin|Bilirubin)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mg/dl|mg\/dl)",
        ],
        "alt": [
            r"(?:ALT|SGPT)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:IU/l|U/L)",
        ],
        "ast": [
            r"(?:AST|SGOT)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:IU/l|U/L)",
        ],
        "diseases_conditions": [
            r"(?:Diagnosis|Impression|Condition|Disease)\s*[:=]?\s*([^\n]+)",
            r"(?:History of|Presenting with|Chief complaint|Symptoms?)\s*[:=]?\s*([^\n]+)",
        ],
    }
    
    # Normal value ranges for common medical measurements
    NORMAL_RANGES = {
        "blood_pressure_systolic": (90, 120),  # mmHg
        "blood_pressure_diastolic": (60, 80),  # mmHg
        "blood_sugar": (100, 125),  # mg/dL (fasting)
        "hemoglobin": (12, 17.5),  # g/dL
        "cholesterol": (0, 200),  # mg/dL
        "triglycerides": (0, 150),  # mg/dL
        "sodium": (135, 145),  # mEq/L
        "potassium": (3.5, 5.0),  # mEq/L
        "creatinine": (0.6, 1.2),  # mg/dL
        "bilirubin": (0.1, 1.2),  # mg/dL
        "alt": (0, 40),  # IU/L
        "ast": (0, 40),  # IU/L
    }
    
    # Critical thresholds for alerts
    CRITICAL_THRESHOLDS = {
        "blood_sugar": {"low": 70, "high": 250},
        "hemoglobin": {"low": 7, "high": 20},
        "blood_pressure_systolic": {"low": 80, "high": 180},
        "blood_pressure_diastolic": {"low": 50, "high": 120},
        "cholesterol": {"low": 0, "high": 300},
        "creatinine": {"high": 3.0},
    }
    
    # Keywords for critical conditions
    CRITICAL_KEYWORDS = {
        "emergency": ["acute", "emergency", "critical", "severe", "life-threatening"],
        "heart": ["myocardial", "infarction", "mi", "heart attack", "cardiac arrest"],
        "bleeding": ["hemorrhage", "bleeding", "acute bleed", "massive bleed"],
        "respiratory": ["respiratory failure", "acute respiratory", "asphyxia"],
        "neurological": ["stroke", "cva", "seizure", "coma", "unconscious"],
        "infection": ["sepsis", "septic", "acute infection", "acute pneumonia"],
        "trauma": ["trauma", "fracture", "compound fracture", "internal injury"],
    }
    
    # Medicine suggestions mapping based on detected conditions/abnormalities
    MEDICINE_SUGGESTIONS = {
        "High": {
            "Blood Pressure": ["Amlodipine", "Lisinopril", "Metoprolol"],
            "Blood Sugar": ["Metformin", "Glipizide", "Insulin"],
            "Total Cholesterol": ["Atorvastatin", "Simvastatin", "Rosuvastatin"],
            "Triglycerides": ["Fenofibrate", "Gemfibrozil"],
        },
        "Low": {
            "Blood Pressure": ["Fludrocortisone", "Midodrine"],
            "Blood Sugar": ["Glucose tablets", "Dextrose", "Glucagon"],
            "Hemoglobin": ["Ferrous sulfate", "Iron supplementation"],
        },
        "Low (Anemia)": {
            "Hemoglobin": ["Ferrous sulfate", "Iron supplementation", "Vitamin B12"],
        },
        "Elevated (Possible liver issues)": {
            "ALT": ["Silymarin (Milk Thistle)", "N-Acetylcysteine"],
            "AST": ["Silymarin (Milk Thistle)", "N-Acetylcysteine"],
        },
        "High (Possible kidney issues)": {
            "Creatinine": ["ACE Inhibitors", "ARBs", "Dietary adjustments"],
        },
        "Critical Low": {
            "Blood Sugar": ["Urgent glucose administration", "Glucagon injection"],
        }
    }
    
    # Lifestyle recommendations based on conditions
    LIFESTYLE_RECOMMENDATIONS = {
        "High Blood Pressure": [
            "Reduce salt intake to less than 2,300 mg per day",
            "Exercise regularly: 150 minutes per week of moderate activity",
            "Maintain a healthy weight",
            "Limit alcohol consumption",
            "Manage stress through relaxation techniques"
        ],
        "High Blood Sugar": [
            "Eat a balanced diet low in sugar and refined carbohydrates",
            "Exercise at least 150 minutes per week",
            "Maintain healthy body weight",
            "Monitor blood glucose regularly",
            "Drink plenty of water and avoid sugary beverages"
        ],
        "High Cholesterol": [
            "Reduce saturated fat intake",
            "Eat more fiber-rich foods (whole grains, vegetables, fruits)",
            "Exercise regularly for at least 30 minutes daily",
            "Maintain healthy weight",
            "Avoid trans fats and processed foods"
        ],
        "Low Hemoglobin": [
            "Increase iron-rich foods (red meat, spinach, lentils, beans)",
            "Consume foods rich in Vitamin C to enhance iron absorption",
            "Avoid excessive caffeine as it can inhibit iron absorption",
            "Rest adequately to allow the body to recover",
            "Follow up with doctor for further testing if symptoms persist"
        ],
        "Kidney Issues": [
            "Reduce sodium intake",
            "Monitor protein consumption",
            "Stay well hydrated",
            "Avoid excessive potassium intake",
            "Regular follow-up with healthcare provider"
        ],
        "Liver Issues": [
            "Avoid alcohol completely",
            "Eat a healthy, balanced diet",
            "Maintain healthy weight",
            "Stay hydrated",
            "Avoid over-the-counter medications without consulting doctor"
        ]
    }
    
    def __init__(self):
        """Initialize the analyzer."""
        self.extracted_data = {}
        self.warnings = []
        self.abnormalities = []
        
    def extract_text_from_file(self, file_path: str) -> str:
        """
        Extract text from a file (PDF or plain text).
        Intelligently detects file type from extension and content.
        
        Args:
            file_path: Path to the file to extract text from
            
        Returns:
            Extracted text from the file
            
        Raises:
            ValueError: If file type is not supported or pdfplumber is not available
        """
        path = Path(file_path)
        file_suffix = path.suffix.lower()
        
        # Try to detect file type from magic bytes if extension is missing/unclear
        is_pdf = False
        is_text = False
        
        if file_suffix == ".pdf" or file_suffix == "":
            # Check if it's actually a PDF by reading magic bytes
            try:
                with open(file_path, 'rb') as f:
                    header = f.read(4)
                    if header == b'%PDF':  # PDF magic bytes
                        is_pdf = True
            except:
                pass
        
        if file_suffix in [".txt", ".text"]:
            is_text = True
        elif file_suffix == "" and not is_pdf:
            # No extension, try to read as text first
            is_text = True
        
        # Handle PDF files
        if is_pdf or file_suffix == ".pdf":
            if pdfplumber is None:
                raise ValueError(
                    "PDF support requires pdfplumber. Install with: pip install pdfplumber"
                )
            try:
                text = ""
                with pdfplumber.open(file_path) as pdf:
                    for page in pdf.pages:
                        text += page.extract_text() or ""
                return text
            except Exception as e:
                raise ValueError(f"Failed to extract text from PDF: {str(e)}")
        
        # Handle plain text files
        elif is_text or file_suffix in [".txt", ".text"]:
            try:
                return path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                raise ValueError(f"Failed to read text file: {str(e)}")
        
        else:
            raise ValueError(f"Unsupported file type: {file_suffix}. Supported types: .pdf, .txt, .text")
    
    def extract_value_from_text(self, text: str, patterns: List[str]) -> Optional[str]:
        """
        Extract a value from text using a list of regex patterns.
        
        Args:
            text: Text to search in
            patterns: List of regex patterns to try
            
        Returns:
            Extracted value or None if not found
        """
        text_lower = text.lower()
        
        for pattern in patterns:
            try:
                # Case-insensitive search
                matches = re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE)
                for match in matches:
                    if match.groups():
                        # Return the first group (most specific value)
                        return match.group(1).strip()
                    else:
                        # Return the full match if no groups
                        return match.group(0).strip()
            except re.error:
                continue
        
        return None
    
    def extract_blood_pressure(self, text: str) -> Tuple[Optional[float], Optional[float]]:
        """
        Extract blood pressure (systolic, diastolic) from text.
        
        Args:
            text: Text to search in
            
        Returns:
            Tuple of (systolic, diastolic) values or (None, None)
        """
        for pattern in self.PATTERNS["blood_pressure"]:
            try:
                matches = re.finditer(pattern, text, re.IGNORECASE)
                for match in matches:
                    if len(match.groups()) >= 2:
                        try:
                            systolic = float(match.group(1))
                            diastolic = float(match.group(2))
                            if 60 <= systolic <= 250 and 40 <= diastolic <= 150:
                                return systolic, diastolic
                        except (ValueError, IndexError):
                            continue
            except re.error:
                continue
        
        return None, None
    
    def analyze_medical_values(self, text: str) -> Dict:
        """
        Extract and analyze medical values from the report text.
        
        Args:
            text: Text from the medical report
            
        Returns:
            Dictionary with extracted medical values
        """
        data = {}
        
        # Extract patient name
        name = self.extract_value_from_text(text, self.PATTERNS["patient_name"])
        data["patient_name"] = name if name and len(name) > 2 else "Not specified"
        
        # Extract age
        age = self.extract_value_from_text(text, self.PATTERNS["age"])
        if age:
            try:
                data["age"] = int(age)
            except ValueError:
                data["age"] = None
        else:
            data["age"] = None
        
        # Extract blood pressure
        systolic, diastolic = self.extract_blood_pressure(text)
        if systolic and diastolic:
            data["blood_pressure"] = f"{int(systolic)}/{int(diastolic)}"
        else:
            data["blood_pressure"] = None
        
        # Extract other common values
        for key in ["blood_sugar", "hemoglobin", "cholesterol", "triglycerides", 
                    "sodium", "potassium", "creatinine", "bilirubin", "alt", "ast"]:
            value = self.extract_value_from_text(text, self.PATTERNS[key])
            if value:
                try:
                    # Try to convert to float
                    data[key] = float(value)
                except ValueError:
                    data[key] = value
            else:
                data[key] = None
        
        # Extract diseases/conditions
        conditions = self.extract_value_from_text(text, self.PATTERNS["diseases_conditions"])
        data["diseases_conditions"] = conditions if conditions else "Not specified"
        
        self.extracted_data = data
        return data
    
    def detect_abnormalities(self, data: Dict) -> List[Dict]:
        """
        Detect abnormal values based on normal ranges.
        
        Args:
            data: Dictionary of extracted medical values
            
        Returns:
            List of abnormality alerts
        """
        abnormalities = []
        
        # Check blood pressure
        if data.get("blood_pressure"):
            try:
                bp_parts = str(data["blood_pressure"]).split("/")
                if len(bp_parts) == 2:
                    systolic = float(bp_parts[0])
                    diastolic = float(bp_parts[1])
                    
                    if systolic > 140 or diastolic > 90:
                        abnormalities.append({
                            "parameter": "Blood Pressure",
                            "value": data["blood_pressure"],
                            "status": "High",
                            "severity": "warning"
                        })
                    elif systolic < 90 or diastolic < 60:
                        abnormalities.append({
                            "parameter": "Blood Pressure",
                            "value": data["blood_pressure"],
                            "status": "Low",
                            "severity": "warning"
                        })
            except (ValueError, TypeError):
                pass
        
        # Check blood sugar
        if data.get("blood_sugar"):
            try:
                bs = float(data["blood_sugar"])
                if bs > 180:
                    abnormalities.append({
                        "parameter": "Blood Sugar",
                        "value": f"{bs} mg/dL",
                        "status": "High",
                        "severity": "warning"
                    })
                elif bs < 70:
                    abnormalities.append({
                        "parameter": "Blood Sugar",
                        "value": f"{bs} mg/dL",
                        "status": "Critical Low",
                        "severity": "critical"
                    })
            except (ValueError, TypeError):
                pass
        
        # Check hemoglobin
        if data.get("hemoglobin"):
            try:
                hb = float(data["hemoglobin"])
                if hb < 12:
                    abnormalities.append({
                        "parameter": "Hemoglobin",
                        "value": f"{hb} g/dL",
                        "status": "Low (Anemia)",
                        "severity": "warning"
                    })
                elif hb > 17.5:
                    abnormalities.append({
                        "parameter": "Hemoglobin",
                        "value": f"{hb} g/dL",
                        "status": "High",
                        "severity": "warning"
                    })
            except (ValueError, TypeError):
                pass
        
        # Check cholesterol
        if data.get("cholesterol"):
            try:
                chol = float(data["cholesterol"])
                if chol > 240:
                    abnormalities.append({
                        "parameter": "Total Cholesterol",
                        "value": f"{chol} mg/dL",
                        "status": "High",
                        "severity": "warning"
                    })
            except (ValueError, TypeError):
                pass
        
        # Check creatinine (kidney function)
        if data.get("creatinine"):
            try:
                creat = float(data["creatinine"])
                if creat > 1.2:
                    abnormalities.append({
                        "parameter": "Creatinine",
                        "value": f"{creat} mg/dL",
                        "status": "High (Possible kidney issues)",
                        "severity": "warning"
                    })
            except (ValueError, TypeError):
                pass
        
        # Check ALT/AST (liver function)
        for param, key in [("ALT", "alt"), ("AST", "ast")]:
            if data.get(key):
                try:
                    value = float(data[key])
                    if value > 40:
                        abnormalities.append({
                            "parameter": param,
                            "value": f"{value} IU/L",
                            "status": "Elevated (Possible liver issues)",
                            "severity": "warning"
                        })
                except (ValueError, TypeError):
                    pass
        
        self.abnormalities = abnormalities
        return abnormalities
    
    def suggest_medicines(self, abnormalities: List[Dict]) -> Dict:
        """
        Suggest medicines based on detected abnormalities.
        
        Args:
            abnormalities: List of detected abnormalities
            
        Returns:
            Dictionary with medicine suggestions and recommendations
        """
        suggested_medicines = []
        recommendations = []
        medicine_details = {}
        
        # Map abnormalities to medicine suggestions
        for abnormality in abnormalities:
            status = abnormality.get("status", "")
            parameter = abnormality.get("parameter", "")
            
            # Check if we have suggestions for this status/parameter combination
            if status in self.MEDICINE_SUGGESTIONS:
                if parameter in self.MEDICINE_SUGGESTIONS[status]:
                    medicines = self.MEDICINE_SUGGESTIONS[status][parameter]
                    suggested_medicines.extend(medicines)
                    
                    if parameter not in medicine_details:
                        medicine_details[parameter] = {
                            "parameter": parameter,
                            "status": status,
                            "medicines": medicines,
                            "severity": abnormality.get("severity", "warning")
                        }
        
        # Add lifestyle recommendations based on abnormalities
        for abnormality in abnormalities:
            parameter = abnormality.get("parameter", "")
            status = abnormality.get("status", "")
            
            # Map parameters to lifestyle recommendation categories
            if "Blood Pressure" in parameter and status:
                if "High" in status:
                    recommendations.extend(self.LIFESTYLE_RECOMMENDATIONS.get("High Blood Pressure", []))
                elif "Low" in status:
                    recommendations.append("Increase salt and fluid intake")
                    recommendations.append("Avoid prolonged standing")
                    recommendations.append("Eat small, frequent meals")
            
            elif "Blood Sugar" in parameter and status:
                if "High" in status:
                    recommendations.extend(self.LIFESTYLE_RECOMMENDATIONS.get("High Blood Sugar", []))
                elif "Low" in status:
                    recommendations.extend(["Carry fast-acting carbohydrates", "Eat regular meals"])
            
            elif "Cholesterol" in parameter:
                recommendations.extend(self.LIFESTYLE_RECOMMENDATIONS.get("High Cholesterol", []))
            
            elif "Hemoglobin" in parameter:
                recommendations.extend(self.LIFESTYLE_RECOMMENDATIONS.get("Low Hemoglobin", []))
            
            elif "Creatinine" in parameter or "kidney" in parameter.lower():
                recommendations.extend(self.LIFESTYLE_RECOMMENDATIONS.get("Kidney Issues", []))
            
            elif "ALT" in parameter or "AST" in parameter:
                recommendations.extend(self.LIFESTYLE_RECOMMENDATIONS.get("Liver Issues", []))
        
        # Remove duplicates from suggestions and recommendations
        suggested_medicines = list(set(suggested_medicines))
        recommendations = list(set(recommendations))
        
        return {
            "medicines": suggested_medicines,
            "medicine_details": medicine_details,
            "lifestyle_recommendations": recommendations,
            "note": "These are general suggestions. Please consult with a healthcare professional before taking any medication."
        }
    
    def detect_critical_keywords(self, text: str) -> List[str]:
        """
        Detect critical health conditions based on keywords.
        
        Args:
            text: Text to search for critical keywords
            
        Returns:
            List of detected critical conditions
        """
        detected_conditions = []
        text_lower = text.lower()
        
        for condition_type, keywords in self.CRITICAL_KEYWORDS.items():
            for keyword in keywords:
                if keyword in text_lower:
                    detected_conditions.append(condition_type.capitalize())
        
        return list(set(detected_conditions))  # Remove duplicates
    
    def determine_risk_level(self, data: Dict, abnormalities: List[Dict], 
                            critical_keywords: List[str]) -> str:
        """
        Determine overall risk level based on detected abnormalities.
        
        Args:
            data: Extracted medical data
            abnormalities: List of detected abnormalities
            critical_keywords: List of detected critical conditions
            
        Returns:
            Risk level: "Normal", "Warning", or "Critical"
        """
        # If critical keywords detected, return Critical
        if critical_keywords:
            return "Critical"
        
        # If critical severity abnormalities, return Critical
        if any(ab.get("severity") == "critical" for ab in abnormalities):
            return "Critical"
        
        # If warning severity abnormalities, return Warning
        if any(ab.get("severity") == "warning" for ab in abnormalities):
            return "Warning"
        
        # Otherwise Normal
        return "Normal"
    
    def generate_summary(self, data: Dict, abnormalities: List[Dict]) -> str:
        """
        Generate a brief medical summary.
        
        Args:
            data: Extracted medical data
            abnormalities: List of abnormalities
            
        Returns:
            Summary text
        """
        parts = []
        
        # Patient info
        name = data.get("patient_name", "Unknown")
        age = data.get("age")
        if age:
            parts.append(f"Patient {name}, Age {age}")
        else:
            parts.append(f"Patient {name}")
        
        # Medical findings
        if abnormalities:
            abnorm_list = [f"{ab['parameter']} ({ab['status']})" for ab in abnormalities]
            parts.append(f"Findings: {', '.join(abnorm_list)}")
        else:
            parts.append("No significant abnormalities detected")
        
        # Conditions
        conditions = data.get("diseases_conditions", "")
        if conditions and conditions != "Not specified":
            parts.append(f"Reported conditions: {conditions}")
        
        return ". ".join(parts)
    
    def analyze_report(self, file_path: str) -> Dict:
        """
        Main analysis function - orchestrates the complete analysis pipeline.
        
        Args:
            file_path: Path to the medical report file
            
        Returns:
            Dictionary with analysis results
        """
        try:
            # Step 1: Extract text from file
            text = self.extract_text_from_file(file_path)
            
            # Step 2: Extract medical values
            medical_data = self.analyze_medical_values(text)
            
            # Step 3: Detect abnormalities
            abnormalities = self.detect_abnormalities(medical_data)
            
            # Step 4: Suggest medicines based on abnormalities
            medicine_suggestions = self.suggest_medicines(abnormalities)
            
            # Step 5: Detect critical keywords
            critical_keywords = self.detect_critical_keywords(text)
            
            # Step 6: Determine risk level
            risk_level = self.determine_risk_level(medical_data, abnormalities, critical_keywords)
            
            # Step 7: Generate summary
            summary = self.generate_summary(medical_data, abnormalities)
            
            # Build result
            result = {
                "success": True,
                "patient_name": medical_data.get("patient_name", "Not specified"),
                "age": medical_data.get("age"),
                "blood_pressure": medical_data.get("blood_pressure"),
                "blood_sugar": medical_data.get("blood_sugar"),
                "hemoglobin": medical_data.get("hemoglobin"),
                "cholesterol": medical_data.get("cholesterol"),
                "other_values": {
                    "triglycerides": medical_data.get("triglycerides"),
                    "sodium": medical_data.get("sodium"),
                    "potassium": medical_data.get("potassium"),
                    "creatinine": medical_data.get("creatinine"),
                    "bilirubin": medical_data.get("bilirubin"),
                    "alt": medical_data.get("alt"),
                    "ast": medical_data.get("ast"),
                },
                "diseases_conditions": medical_data.get("diseases_conditions"),
                "abnormalities": abnormalities,
                "critical_keywords": critical_keywords,
                "risk_level": risk_level,
                "summary": summary,
                "suggested_medicines": medicine_suggestions.get("medicines", []),
                "medicine_details": medicine_suggestions.get("medicine_details", {}),
                "lifestyle_recommendations": medicine_suggestions.get("lifestyle_recommendations", []),
                "medicine_note": medicine_suggestions.get("note", ""),
                "full_data": medical_data,
            }
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to analyze medical report"
            }


def analyze_medical_report(file_path: str) -> Dict:
    """
    Convenience function to analyze a medical report.
    
    Args:
        file_path: Path to the medical report file (PDF or TXT)
        
    Returns:
        Dictionary with analysis results including extracted medical values,
        detected abnormalities, risk level, and summary
    """
    analyzer = MedicalReportAnalyzer()
    return analyzer.analyze_report(file_path)
