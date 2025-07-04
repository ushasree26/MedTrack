from flask import Flask, render_template, request, redirect, url_for, session, flash
import boto3
from boto3.dynamodb.conditions import Key
import os
import uuid
from datetime import datetime
import smtplib
from email.mime.text import MIMEText

app = Flask(__name__)
app.secret_key = 'sreeusha790'

USE_DYNAMODB = True  # Set to True when deploying on AWS
AWS_REGION = 'us-east-1'

if USE_DYNAMODB:
    dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
    users_table = dynamodb.Table('Users')
    appointments_table = dynamodb.Table('Appointments')
    prescriptions_table = dynamodb.Table('Prescriptions')
    medications_table = dynamodb.Table('Medications')
    
def send_local_email(to_email, subject, body):
    try:
        smtp_server = 'smtp.gmail.com'
        smtp_port = 587
        sender_email = os.getenv('SENDER_EMAIL')
        sender_password = os.getenv('SENDER_PASSWORD')    

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = sender_email
        msg['To'] = to_email

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()

        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Email sending failed: {e}")
SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:241533142623:MedTrackNotification:5b6ddd93-7912-437c-ba65-272244d944f5"
sns = boto3.client('sns', region_name='us-east-1')
def send_sns_email(subject, message):
    try:
        sns.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=message,
            Subject=subject
        )
        print("📨 SNS email sent successfully.")
    except Exception as e:
        print(f"❌ Failed to send SNS email: {e}")

def send_local_sms(phone, message):
    print(f"[SIMULATED SMS to {phone}]: {message}")

db = {
    'users': {
        "dr.john@example.com": {
            "name": "Dr. John", "password": "doc123", "role": "doctor", "phone": "1234567890", "reminder": "Daily"
        },
        "patient.rita@example.com": {
            "name": "Rita", "password": "pat456", "role": "patient", "phone": "9876543210", "reminder": "Weekly"
        }
    },
    'appointments': [],
    'prescriptions': [],
    'medications': []
}
def load_users():
    if USE_DYNAMODB:
        response = users_table.scan()
        return {item['email']: item for item in response.get('Items', [])}
    else:
        return db['users']

def load_appointments():
    if USE_DYNAMODB:
        response = appointments_table.scan()
        return response.get('Items', [])
    else:
        return db['appointments']
    
def save_appointment(appt):
    if USE_DYNAMODB:
        appointments_table.put_item(Item=appt)
    else:
        db['appointments'].append(appt)

def save_prescription(presc):
    if USE_DYNAMODB:
        prescriptions_table.put_item(Item=presc)
    else:
        db['prescriptions'].append(presc)

def save_medication(med):
    if USE_DYNAMODB:
        medications_table.put_item(Item=med)
    else:
        db['medications'].append(med)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/doctorreview')
def doctorreview():
    return render_template('doctorreview.html')

@app.route('/patientreview')
def patientreview():
    return render_template('patientreview.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        data = {
            'name': request.form['name'],
            'email': request.form['email'],
            'password': request.form['password'],
            'phone': request.form['phone'],
            'role': request.form['role'],
            'reminder': request.form['reminder']
        }

        users = load_users()
        if data['email'] in users:
            flash("Email already exists", "error")
            return redirect(url_for('signup'))
            
        if USE_DYNAMODB:
            try:
                users_table.put_item(Item=data)
            except Exception as e:
                flash(f"Failed to register user: {e}", "error")
                return redirect(url_for('signup'))
        else:
            db['users'][data['email']] = data

        subject = "🎉 Welcome to MedTrack!"
        message = f"Hi {data['name']},\n\nYou have successfully registered in the MedTrack app.\n\nStay healthy!"
        send_sns_email(subject, message)

        flash("Signup successful! Now login.", "success")
        return redirect(url_for('login'))

    return render_template('signup.html')


from werkzeug.security import check_password_hash

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        users = load_users()
        user = users.get(email)

        if user:
            # Handle hashed or plain password
            stored_password = user['password']
            if (stored_password == password) or (check_password_hash(stored_password, password)):
                session.update({
                    "email": email,
                    "role": user['role'],
                    "name": user['name'],
                    "phone": user.get('phone', '')
                })
                return redirect(url_for(f"{user['role']}dashboard"))
        
        flash("Invalid credentials", "error")
    return render_template('login.html')

@app.route('/appointment', methods=['GET', 'POST'])
def appointment():
    if request.method == 'POST':
        f = request.form
        appt = {
            'id': str(uuid.uuid4()), 'patient': session.get('name'), 'name': f['name'], 'gender': f['gender'],
            'phone': f['phone'], 'age': f['age'], 'email': session.get('email'),
            'department': f['department'], 'problem': f['problem'], 'doctor': f['doctor'],
            'status': 'Pending', 'date': f['date'], 'time': f['time']
        }
        save_appointment(appt)
        flash("Appointment booked successfully!", "success")
        return redirect(url_for('appointment'))
    return render_template('appointment.html')

@app.route('/send_notifications')
def send_notifications():
    now = datetime.now()
    current_time = now.strftime("%H:%M")
    today = now.strftime("%Y-%m-%d")
    reminders_sent = 0

    for med in db['medications']:
        med_time = datetime.strptime(med['time'], "%I:%M %p").strftime("%H:%M")
        med_date = med.get('date', today)  # Optional date field
        if med['status'].lower() == 'pending' and med_time == current_time and med_date == today:
            # Send SNS email reminder
            subject = f"💊 Medication Reminder: {med['medicine']}"
            message = f"Dear {med['patient']},\n\nThis is your MedTrack reminder to take {med['medicine']} at {med['time']} today.\n\nStay healthy!"
            send_sns_email(subject, message)

            med['status'] = 'Sent'  
            reminders_sent += 1

    return f"{reminders_sent} reminder(s) sent."
@app.route('/doctordashboard', methods=['GET', 'POST'])
def doctordashboard():
    if session.get('role') != 'doctor':
        return redirect(url_for('login'))

    name = session['name']
    doctor_appts = [a for a in db['appointments'] if a['doctor'].strip().lower() == name.strip().lower()]

    now = datetime.now()
    for appt in doctor_appts:
        appt_time_str = f"{appt['date']} {appt['time']}"
        try:
            appt_time = datetime.strptime(appt_time_str, "%Y-%m-%d %H:%M")
        except ValueError:
            continue
        if appt['status'] == 'Pending' and now > appt_time:
            appt['status'] = 'Missed'

    alerts = []
    for m in db['medications']:
        if m['status'].lower() == 'missed':
            alerts.append(f"Patient {m['patient']} missed dose of {m['medicine']} at {m['time']}")

    if request.method == 'POST':
        decision = request.form['decision']
        appt_id = request.form['appointment_id']
        for a in db['appointments']:
            if a['id'] == appt_id:
                a['status'] = decision
                break
        flash(f"Appointment {decision.lower()}ed.", "info")

    return render_template('doctordashboard.html',
                           name=name,
                           email=session['email'],
                           appointments=doctor_appts,
                           alerts=alerts)
@app.route('/update-profile', methods=['POST'])
def update_profile():
    if 'email' not in session or 'role' not in session:
        return redirect(url_for('login'))

    email = session['email']
    role = session['role']
    users = load_users()

    if email not in users:
        flash("User not found", "error")
        return redirect(url_for(f'{role}dashboard'))

    user = users[email]
    user['name'] = request.form['name']
    user['email'] = request.form['email']
    user['phone'] = request.form['phone']

    # Update session values
    session['name'] = user['name']
    session['email'] = user['email']
    session['phone'] = user['phone']

    if not USE_DYNAMODB:
        db['users'][email] = user
    else:
        users_table.put_item(Item=user)

    flash("Profile updated successfully.", "success")
    return redirect(url_for(f'{role}dashboard'))


@app.route('/prescribe/<appt_id>', methods=['GET', 'POST'])
def prescribe(appt_id):
    if request.method == 'POST':
        f = request.form
        time = f"{f['time']} {f['ampm']}" if 'ampm' in f else f['time']
        presc = {
            'id': str(uuid.uuid4()), 'appointment_id': appt_id, 'medicine': f['medicine'],
            'dosage': f['dosage'], 'days_left': f['days_left'], 'time': time,
            'status': 'Pending', 'patient': f['patient']
        }
        save_prescription(presc)
        save_medication(presc)
        flash("Prescription added & medication reminder set.", "success")
        return redirect(url_for('doctordashboard'))
    appt = next((a for a in db['appointments'] if a['id'] == appt_id), None)
    return render_template('prescribe.html', appointment=appt)

@app.route('/patientdashboard')
def patientdashboard():
    if session.get('role') != 'patient':
        return redirect(url_for('login'))

    name = session.get('name')
    email = session.get('email')

    user_appointments = [appt for appt in db['appointments'] if appt['patient'] == name]
    
    now = datetime.now()
    for appt in user_appointments:
        appt_time_str = f"{appt['date']} {appt['time']}"
        try:
            appt_time = datetime.strptime(appt_time_str, "%Y-%m-%d %H:%M")
        except ValueError:
            appt_time = now  # fallback if formatting is bad

        if appt['status'] == 'Pending' and now > appt_time:
            appt['status'] = 'Missed'

    user_medications = [med for med in db['medications'] if med['patient'] == name]
    user_prescriptions = [p for p in load_prescriptions() if p['patient'] == name]

    alerts = []
    for med in user_medications:
        med_time_str = f"{med.get('date', now.strftime('%Y-%m-%d'))} {med['time'].split()[0]}"

        try:
            med_time = datetime.strptime(med_time_str, "%Y-%m-%d %H:%M")
        except:
            continue
        if med['status'] == 'Pending' and now > med_time:
            med['status'] = 'Missed'
            alerts.append(f"You missed your dose of {med['medicine']} at {med['time']} on {med.get('date', 'N/A')}")

    return render_template("patientdashboard.html",
                           name=name,
                           email=email,
                           appointments=user_appointments,
                           medications=user_medications,
                           prescriptions=user_prescriptions,
                           alerts=alerts)


@app.route('/addmedication', methods=['GET', 'POST'])
def addmedication():
    if session.get('role') != 'patient': return redirect(url_for('login'))
    if request.method == 'POST':
        f = request.form
        med = {
            'id': str(uuid.uuid4()), 'patient': session['name'], 'medicine': f['medicine'],'date': f['date'],
            'dosage': f['dosage'], 'time': f['time'], 'days_left': f['days_left'], 'status': f.get('status', 'Pending')
        }
        save_medication(med)
        flash("Medication added successfully.", "success")
        return redirect(url_for('patientdashboard'))
    return render_template('addmedication.html')

@app.route('/aboutus')
def aboutus():
    return render_template('aboutus.html')

@app.route('/contactus', methods=['GET', 'POST'])
def contactus():
    if request.method == 'POST':
        flash("Message sent successfully. Thank you for contacting MedTrack!", 'success')
        return redirect(url_for('contactus'))
    return render_template('contactus.html')

@app.route('/update_medication_status', methods=['POST'])
def update_medication_status():
    
    if session.get('role') != 'patient':
        return redirect(url_for('login'))

    for med in db['medications']:
        form_key = f"status_{med['id']}"
        if form_key in request.form:
            new_status = request.form[form_key]
            current_time = datetime.now().strftime("%H:%M")
            if new_status == "Not Yet" and current_time > med['time']:
                med['status'] = "Missed"
            else:
                med['status'] = "Completed" if new_status == "Taken" else "Pending"

    flash("Medication status updated.", "success")
    return redirect(url_for('patientdashboard'))

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))
    
def load_prescriptions():
    if USE_DYNAMODB:
        response = prescriptions_table.scan()
        return response.get('Items', [])
    else:
        return db['prescriptions']
        
if __name__ == '__main__':
    app.run(debug=True)
