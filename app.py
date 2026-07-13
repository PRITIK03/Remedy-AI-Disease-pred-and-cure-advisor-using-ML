from flask import Flask, render_template, request
import numpy as np
import pickle

app = Flask(__name__)

# Load the models and scaler
with open(r'C:\Users\priti\OneDrive\Desktop\MY_Project\Models\logistic_regression_model.pkl', 'rb') as f:
    logistic_regression_model = pickle.load(f)

with open(r'C:\Users\priti\OneDrive\Desktop\MY_Project\Models\random_forest_model.pkl', 'rb') as f:
    random_forest_model = pickle.load(f)

with open(r'C:\Users\priti\OneDrive\Desktop\MY_Project\Models\voting_classifier_model.pkl', 'rb') as f:
    voting_classifier_model = pickle.load(f)

with open(r'C:\Users\priti\OneDrive\Desktop\MY_Project\Models\scaler.pkl', 'rb') as f:
    scaler = pickle.load(f)

# Function to provide remedies based on input features and predicted risk
def get_remedies(features, predicted_risk):
    remedies = []

    if predicted_risk > 0.5:  # High risk
        remedies.append("Consult a healthcare professional immediately for a thorough evaluation.")
    
    if features['age'] > 50:
        remedies.append("Schedule regular check-ups with your doctor.")
    
    if features['chol'] > 200:
        remedies.append("Adopt a heart-healthy diet low in saturated fats and high in fruits, vegetables, and whole grains.")
    
    if features['trestbps'] > 130:
        remedies.append("Monitor your blood pressure regularly and consider lifestyle changes to lower it.")
    
    if features['thalach'] < 120:
        remedies.append("Improve your cardiovascular fitness through regular aerobic exercise.")
    
    if features['oldpeak'] > 1:
        remedies.append("Discuss stress test results with your doctor and consider cardiac rehabilitation if recommended.")
    
    remedies.append("Maintain a healthy weight through a balanced diet and regular exercise.")
    remedies.append("If you smoke, quit smoking or seek support to help you quit.")
    remedies.append("Limit alcohol consumption to no more than one drink per day for women and two for men.")
    remedies.append("Aim for at least 150 minutes of moderate-intensity exercise per week.")
    remedies.append("Manage stress through relaxation techniques like meditation or yoga.")
    remedies.append("Ensure you're getting 7-9 hours of quality sleep each night.")
    
    return remedies

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/predict', methods=['POST'])
def predict():
    # Get the input values from the form
    age = int(request.form['age'])
    sex = int(request.form['sex'])
    cp = int(request.form['cp'])
    trestbps = int(request.form['trestbps'])
    chol = int(request.form['chol'])
    fbs = int(request.form['fbs'])
    restecg = int(request.form['restecg'])
    thalach = int(request.form['thalach'])
    exang = int(request.form['exang'])
    oldpeak = float(request.form['oldpeak'])
    slope = int(request.form['slope'])
    ca = int(request.form['ca'])
    thal = int(request.form['thal'])

    # Create a NumPy array from the inputs
    input_data = np.array([[age, sex, cp, trestbps, chol, fbs, restecg, thalach, exang, oldpeak, slope, ca, thal]])

    # Standardize the input data
    input_data_scaled = scaler.transform(input_data)

    # Make the prediction using the voting classifier
    prediction_prob = voting_classifier_model.predict_proba(input_data_scaled)[:, 1][0]  # Get probability of high risk
    predicted_risk = prediction_prob * 100  # Convert to percentage

    # Create a dictionary of features for remedy generation
    features = {
        'age': age,
        'trestbps': trestbps,
        'chol': chol,
        'thalach': thalach,
        'oldpeak': oldpeak
    }

    # Get remedies based on the predicted risk
    remedies = get_remedies(features, prediction_prob)

    if prediction_prob > 0.5:
        result_text = f"High risk of heart disease: {predicted_risk:.2f}%"
    else:
        result_text = f"Low risk of heart disease: {predicted_risk:.2f}%"

    return render_template('index.html', prediction_result=result_text, remedies=remedies)

if __name__ == '__main__':
    app.run(debug=True)
    }
