HSUSER=headerservice
TAGNAME=6.1.0-10.2.0-salobj_6.9.0-hs_2.9.4 
DOCKER_IMA=lsstdm/headerservice:$TAGNAME
NAME=headerservice

hostname="`hostname -s`-docker"
ip=$(ifconfig en0 | grep inet | awk '$1=="inet" {print $2}')
xhost + $ip


echo "starting docker with image: $DOCKER_IMA"
docker run -ti -e DISPLAY=$ip:0 \
    -h $hostname \
    --network host \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v $HOME/sal-home:/home/$HSUSER \
    --name $NAME \
    $DOCKER_IMA bash

# To re-enter from another terminal
# NAME=headerservice; docker exec -ti $NAME bash

# To clean up
# docker rm $(docker ps -a -f status=exited -q)
