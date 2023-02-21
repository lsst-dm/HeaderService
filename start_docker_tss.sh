TAGNAME=ts-v3.1.8_c0029 
DOCKER_IMA=ts-dockerhub.lsst.org/headerservice:$TAGNAME
NAME=tssheaderservice
HSUSER=saluser


hostname="`hostname -s`-docker"
ip=$(ifconfig en0 | grep inet | awk '$1=="inet" {print $2}')
xhost + $ip


echo "starting docker with image: $DOCKER_IMA"
docker run -ti \
    --entrypoint bash \
    -v $HOME/sal-home:/home/$HSUSER \
    --name $NAME \
    $DOCKER_IMA

# To re-enter from another terminal
# NAME=tssheaderservice; docker exec -ti $NAME bash

# To clean up
# docker rm $(docker ps -a -f status=exited -q)
