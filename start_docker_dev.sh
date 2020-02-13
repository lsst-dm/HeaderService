HSUSER=headerservice
TAGNAME=4.0.0-4.6.0-salobj_5.0.0-aths_1.4.0
DOCKER_IMA=lsstdm/atheaderservice:$TAGNAME
NAME=aths

hostname="`hostname -s`-docker"
ip=$(ifconfig en0 | grep inet | awk '$1=="inet" {print $2}')
xhost + $ip

echo "starting docker with image: $DOCKER_IMA"
docker run -ti -e DISPLAY=$ip:0 \
    -h $hostname \
    -v /tmp/.X11-unix:/tmp/.X11-unix \
    -v $HOME/sal-home:/home/$HSUSER \
    --name $NAME \
    $DOCKER_IMA bash

# To re-enter from another terminal
# docker exec -ti $NAME bash
