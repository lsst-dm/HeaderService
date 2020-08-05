TAGNAME=4.1.4-6.1.0-salobj_5.17.0-hs_2.3.3
DOCKER_IMA=lsstdm/atheaderservice:$TAGNAME
NAME=headerservice

# Make sure we have it
docker pull $DOCKER_IMA

# kill before launching
dockerID=$(docker ps -qa --filter name=$NAME)

if [[ $dockerID> 0 ]]; then
    echo "docker already running as $dockerID..."
    docker rm -f $dockerID
fi

echo "starting docker with image: $DOCKER_IMA"
docker run --network host --name $NAME -td $DOCKER_IMA

# To clean up
# docker rm $(docker ps -a -f status=exited -q)

# To re-enter from another terminal
# docker exec -ti $NAME bash

# To attach to the process
# docker attach -$NAME
