# ==============================================
# REFERENCED
# REASON: The script only utilized when creating new credential for new running a program and sending email, The script only utilzied once when creating local credential to send email
# LEARNINGS: Utilization of powershell script to create environment profile and store into local file
# REFERENCE: Creation of credential utilizing app password from gmail
# ==============================================

# This script is utilized to create local credential, while using app password from gmail

$cred = Get-Credential -Message "Enter email credentials" # Enter existing email
$credDir = "$env:USERPROFILE\.face-recog"
if (-not (Test-Path $credDir)) { New-Item -ItemType Directory -Path $credDir -Force }
$cred | Export-Clixml -Path "$credDir\email-credential.xml" # Enter gmail app password and not our password