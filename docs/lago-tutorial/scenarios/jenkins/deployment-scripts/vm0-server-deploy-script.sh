#!/bin/bash -xe
yum install -y java-1.8.0-openjdk-devel.x86_64 \
  wget \
  net-tools.x86_64


wget -O /etc/yum.repos.d/jenkins.repo http://pkg.jenkins-ci.org/redhat-stable/jenkins.repo
rpm --import http://pkg.jenkins-ci.org/redhat-stable/jenkins-ci.org.key

yum install -y jenkins

# firewall configuration

firewall-cmd --zone=public --add-port=8080/tcp --permanent

firewall-cmd --zone=public --add-service=http --permanent

firewall-cmd --reload

# start jenkins service

service jenkins start

chkconfig jenkins on

