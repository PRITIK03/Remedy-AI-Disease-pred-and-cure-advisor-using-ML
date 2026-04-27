# Remedy-AI: Disease Prediction and Cure Advisor

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0%2B-red)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

## 📋 Overview

**Remedy-AI** is an intelligent disease prediction and cure advisory system that leverages machine learning to assess cardiovascular health risks. The application uses an ensemble of machine learning models (Logistic Regression, Random Forest, and Voting Classifier) to predict the likelihood of heart disease based on patient medical indicators and provides personalized health recommendations.

## 🎯 Features

- **Multiple ML Models**: Ensemble approach combining:
  - Logistic Regression
  - Random Forest
  - Voting Classifier (meta-model)
  
- **Risk Assessment**: Real-time prediction of heart disease risk with probability scoring
- **Personalized Recommendations**: AI-driven health remedies and lifestyle advice based on:
  - Predicted risk level
  - Individual health metrics
  - Age and vital signs
  
- **User-Friendly Interface**: Web-based dashboard for easy input and result visualization
- **Medical Parameter Analysis**: Comprehensive evaluation of 13 health indicators:
  - Age
  - Sex
  - Chest pain type (cp)
  - Resting blood pressure (trestbps)
  - Serum cholesterol (chol)
  - Fasting blood sugar (fbs)
  - Resting electrocardiographic results (restecg)
  - Maximum heart rate achieved (thalach)
  - Exercise-induced angina (exang)
  - ST depression (oldpeak)
  - ST slope (slope)
  - Number of major vessels (ca)
  - Thalassemia type (thal)

## 🏗️ Project Structure

```
Remedy-AI-Disease-pred-and-cure-advisor/
├── app.py                          # Main Flask application
├── Models/                         # Trained ML models directory
│   ├── logistic_regression_model.pkl
│   ├── random_forest_model.pkl
│   ├── voting_classifier_model.pkl
│   └── scaler.pkl                 # StandardScaler for feature normalization
├── templates/
│   └── index.html                 # Web interface
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

## 🛠️ Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager
- Virtual environment (recommended)

### Setup Instructions

1. **Clone the repository**
   ```bash
   git clone https://github.com/PRITIK03/Remedy-AI-Disease-pred-and-cure-advisor.git
   cd Remedy-AI-Disease-pred-and-cure-advisor
   ```

2. **Create a virtual environment** (optional but recommended)
   ```bash
   python -m venv venv
   source venv/bin/activate    # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Update model paths** in `app.py`
   - Replace the hardcoded Windows paths with your local paths:
   ```python
   with open(r'path/to/your/Models/logistic_regression_model.pkl', 'rb') as f:
       logistic_regression_model = pickle.load(f)
   ```

5. **Run the application**
   ```bash
   python app.py
   ```

6. **Access the web interface**
   - Open your browser and navigate to: `http://localhost:5000`

## 📊 How It Works

### 1. **Data Input**
Users enter their medical parameters through the web interface:
- Patient demographics (age, sex)
- Cardiac indicators (blood pressure, cholesterol, heart rate)
- Test results (ECG, stress test findings)

### 2. **Feature Scaling**
Input features are standardized using a pre-fitted StandardScaler to normalize the data for consistent model predictions.

### 3. **Risk Prediction**
The Voting Classifier ensemble model processes the scaled features and outputs:
- Probability of high risk (0-1)
- Percentage-based risk score (0-100%)

### 4. **Personalized Recommendations**
The `get_remedies()` function generates tailored health advice based on:
- Risk level thresholds
- Individual health metrics
- Evidence-based medical guidelines

### 5. **Result Display**
Results are presented with:
- Clear risk classification (High/Low)
- Quantified risk percentage
- Prioritized list of actionable health recommendations

## 🔧 Configuration

### Model Paths
Update the file paths in `app.py` to match your system:

```python
MODEL_DIR = r'path/to/your/Models'
logistic_regression_model = pickle.load(open(f'{MODEL_DIR}/logistic_regression_model.pkl', 'rb'))
random_forest_model = pickle.load(open(f'{MODEL_DIR}/random_forest_model.pkl', 'rb'))
voting_classifier_model = pickle.load(open(f'{MODEL_DIR}/voting_classifier_model.pkl', 'rb'))
scaler = pickle.load(open(f'{MODEL_DIR}/scaler.pkl', 'rb'))
```

### Risk Threshold
Adjust the risk threshold in the `get_remedies()` function if needed:
```python
if predicted_risk > 0.5:  # Currently 50%
    # High risk actions
```

## 📈 Health Metrics Explanation

| Parameter | Range | Description |
|-----------|-------|-------------|
| **Age** | 29-77 years | Patient's age |
| **Sex** | 0=Female, 1=Male | Gender |
| **Chest Pain (cp)** | 0-3 | Type of chest pain experienced |
| **Blood Pressure (trestbps)** | mmHg | Resting blood pressure |
| **Cholesterol (chol)** | mg/dL | Serum cholesterol level |
| **Fasting Blood Sugar (fbs)** | 0=<120, 1=>120 | Fasting blood sugar >120 mg/dL |
| **Resting ECG (restecg)** | 0-2 | Resting electrocardiographic results |
| **Max Heart Rate (thalach)** | bpm | Maximum heart rate achieved |
| **Exercise Angina (exang)** | 0=No, 1=Yes | Exercise-induced chest pain |
| **ST Depression (oldpeak)** | mm | ST segment depression induced by exercise |
| **ST Slope (slope)** | 0-2 | Slope of ST segment during exercise |
| **Major Vessels (ca)** | 0-3 | Number of major vessels colored by fluoroscopy |
| **Thalassemia (thal)** | 0-3 | Type of thalassemia present |

## 🏥 Health Recommendations Generated

The system provides personalized advice including:

✅ Immediate medical consultation if high-risk
✅ Regular health check-ups
✅ Dietary modifications (low-fat, high-fiber)
✅ Blood pressure monitoring and management
✅ Cardiovascular fitness improvements
✅ Cardiac rehabilitation information
✅ Weight management strategies
✅ Smoking cessation support
✅ Alcohol consumption guidelines
✅ Exercise routines (150+ minutes/week)
✅ Stress management techniques
✅ Sleep hygiene recommendations

## 🚀 Usage Example

1. Navigate to `http://localhost:5000`
2. Fill in the medical parameter form with your data
3. Click "Predict" or "Analyze"
4. Review your risk assessment and personalized health recommendations
5. Share results with your healthcare provider

## ⚠️ Important Disclaimer

**This application is for educational and informational purposes only.**

- ❌ **NOT a substitute for professional medical advice**
- ❌ **NOT for diagnosis or treatment of medical conditions**
- ⚠️ **Always consult with a qualified healthcare professional**
- ⚠️ **Do not make medical decisions based solely on this tool**

The predictions generated by this system should be used to complement, not replace, professional medical evaluation.

## 📦 Dependencies

Create a `requirements.txt` file with:

```
Flask==2.3.0
numpy==1.24.0
scikit-learn==1.2.0
pickle5==0.0.12
Werkzeug==2.3.0
```

Install with:
```bash
pip install -r requirements.txt
```

## 🔐 Security Considerations

- [ ] Implement user authentication for production
- [ ] Use environment variables for model paths instead of hardcoding
- [ ] Validate all user inputs
- [ ] Add HTTPS/SSL certificates for production deployment
- [ ] Implement proper error handling and logging
- [ ] Store sensitive health data securely
- [ ] Comply with HIPAA/GDPR regulations for production

## 🐛 Known Issues & Future Improvements

### Current Limitations
- Hard-coded Windows file paths (needs environment-specific configuration)
- No database for storing prediction history
- No user authentication system
- Limited to heart disease prediction

### Planned Enhancements
- [ ] Database integration for prediction history
- [ ] User authentication and profiles
- [ ] Expanded disease prediction models
- [ ] Mobile app version
- [ ] API endpoint for integration with other systems
- [ ] Advanced data visualization and analytics
- [ ] Multi-language support
- [ ] Integration with wearable health devices
- [ ] Real-time monitoring dashboard

## 🤝 Contributing

Contributions are welcome! Please feel free to:
1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 👨‍💻 Author

**PRITIK03**
- GitHub: [@PRITIK03](https://github.com/PRITIK03)

## 📞 Support

For issues, questions, or suggestions:
- Open an issue on GitHub
- Check existing issues for solutions
- Review the documentation above

## 🎓 Educational Resources

Learn more about the concepts used in this project:
- [Machine Learning Fundamentals](https://scikit-learn.org/)
- [Ensemble Methods](https://scikit-learn.org/stable/modules/ensemble.html)
- [Flask Web Framework](https://flask.palletsprojects.com/)
- [Heart Disease Prediction](https://www.kaggle.com/datasets/johnsmith88/heart-disease-dataset)

## 📚 References

- UCI Machine Learning Repository - Heart Disease Dataset
- American Heart Association - Heart Disease Statistics
- Mayo Clinic - Heart Disease Information
- CDC - Heart Disease Data and Statistics

---

**Last Updated**: April 2026
**Version**: 1.0.0

⭐ If you found this project helpful, please consider giving it a star!
