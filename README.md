EC2 Public IP: 3.141.7.60

SSH:

ssh -i "secret_keys/ec2/aws-key.pem" ec2-user@3.141.7.60
scp -i "secret_keys/ec2/aws-key.pem" ec2/app.py ec2-user@3.141.7.60:~

Clean Up:
sudo rm -rf /tmp/_
sudo rm -rf /var/tmp/_

uvicorn websocket:app --host 0.0.0.0 --port 5000
