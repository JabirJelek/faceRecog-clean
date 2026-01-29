# This script is utilized to create local credential, while using app password from gmail

$cred = Get-Credential -Message "Enter email credentials"
$credDir = "$env:USERPROFILE\.face-recog"
if (-not (Test-Path $credDir)) { New-Item -ItemType Directory -Path $credDir -Force }
$cred | Export-Clixml -Path "$credDir\email-credential.xml"