#!/bin/sh

# If there are no packages to update, exit with error
# so we don't change the image for nothing.
if [ $(yum list updates 2>/dev/null | \
       sed '1,/Updated Packages/d' | \
       wc -l) -eq 0 ]
then
	exit 1
fi

yum update -y
