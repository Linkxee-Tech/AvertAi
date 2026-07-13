# AvertAI Frontend & Dashboard

This directory contains the code for both the NGO/Government Admin Dashboard and the Mobile Web App.

## Structure
- `index.html`: The admin dashboard entry point.
- `mobile/index.html`: The mobile app entry point (which is wrapped into an APK via Capacitor).

## Local Development (Powershell)

To run the frontend locally and test against your local backend:

```powershell
# 1. Enter the frontend directory
cd frontend

# 2. Start a simple local web server
python -m http.server 8080
```
Open `http://localhost:8080/index.html` in your browser.

## Cloud Deployment (Firebase Hosting)

We use Firebase Hosting to serve the frontend securely over HTTPS. Follow these commands to deploy your frontend to the cloud:

```powershell
# 1. Enter the frontend directory
cd frontend

# 2. Log in to your Firebase account (uses your muazu0815@gmail.com account)
firebase login

# 3. Deploy the application to your avertai-eef5c project
firebase deploy --only hosting
```

Once deployment is complete, Firebase will provide you with a live URL (e.g., `https://avertai-eef5c.web.app`) which you can share with your stakeholders!
