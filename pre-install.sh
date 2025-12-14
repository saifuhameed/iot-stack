sudo apt update && sudo apt upgrade -y
sudo apt install authbind

cd /etc/authbind
sudo touch /etc/authbind/byport/80

sudo chown debian:debian /etc/authbind/byport/80

sudo systemctl stop nginx

sudo systemctl disable nginx

sudo apt install docker.io docker-compose

sudo usermod -aG docker $USER

git clone https://github.com/saifuhameed/iot-stack.git

#must reboot
#sudo reboot now

cd iot-stack
docker compose build
docker compose up -d






