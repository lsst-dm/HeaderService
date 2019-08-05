# To build:
# docker build -t at_headerservice:sal3.10.0_3.10.0_salobj4.1.0 --rm=true .
# or
# docker build -t at_headerservice --rm=true .
# docker build -t at_headerservice --rm=true --build-arg salobj_image=lsstdm/salobj:<tagname> .
# or
# export TAGNAME=sal_3.10.0-4.0.0_salobj_4.10
# docker build -t at_headerservice:$TAGNAME --build-arg salobj_image=lsstdm/salobj:$TAGNAME .

# Clean up:
# docker rm $(docker ps -a -q)

# To run the HeaderService:
# > source  /opt/lsst/setup_HeaderService.env
# > ATHS_salobj -c $HEADERSERVICE_DIR/etc/conf/atTelemetry_salobj.yaml
# for help:
# > ATHS_salobj  --help

#ARG salobj_image=lsstdm/salobj:sal_3.10.0_salobj_4.10
ARG salobj_image=lsstdm/salobj:sal_3.10.0-4.0.0_salobj_4.10

FROM $salobj_image

# Versions
ARG HEADERSERVICE_VERSION=0.9.8
ARG SALPYTOOLS_VERSION=0.9.7
ARG FITSIO_VERSION=1.0.4
ARG GIT_LSST_DM="https://github.com/lsst-dm"
ARG INSTALL_PATH=/opt/lsst
ARG REPOS_TMP=/tmp/repos
ARG HSUSER=headerservice

RUN pip3 install fitsio==$FITSIO_VERSION

# --- Install HeaderService and salpytools ----
ARG PRODUCT=HeaderService
ARG VERSION=$HEADERSERVICE_VERSION
ARG PRODUCT_DIR=$INSTALL_PATH/$PRODUCT/$VERSION
# Create the init env file
RUN echo "# This loads /opt/lsst/setup_SAL.env" > $INSTALL_PATH/setup_HeaderService.env \
    && echo "source $INSTALL_PATH/setup_salobj.env " >> $INSTALL_PATH/setup_HeaderService.env
# Git clone and version checkout
RUN cd $REPOS_TMP \
    && git clone $GIT_LSST_DM/$PRODUCT.git -b $VERSION\
    && cd $PRODUCT \
    && mkdir -p $PRODUCT_DIR \
    && export PYTHONPATH=$PYTHONPATH:$PRODUCT_DIR/python \
    && python3 setup.py install --prefix=$PRODUCT_DIR --install-lib=$PRODUCT_DIR/python
# Add to the init file
RUN echo "source $PRODUCT_DIR/setpath.sh $PRODUCT_DIR" >> $INSTALL_PATH/setup_HeaderService.env

# Install the salpytools
ARG PRODUCT=salpytools
ARG VERSION=$SALPYTOOLS_VERSION
ARG PRODUCT_DIR=$INSTALL_PATH/$PRODUCT/$VERSION
# Git clone and version checkout
RUN cd $REPOS_TMP \
    && git clone $GIT_LSST_DM/$PRODUCT.git -b $VERSION\
    && cd $PRODUCT \
    && mkdir -p $PRODUCT_DIR \
    && export PYTHONPATH=$PYTHONPATH:$PRODUCT_DIR/python \
    && python3 setup.py install --prefix=$PRODUCT_DIR --install-lib=$PRODUCT_DIR/python

# Add to the init file
RUN echo "source $PRODUCT_DIR/setpath.sh $PRODUCT_DIR" >> $INSTALL_PATH/setup_HeaderService.env
RUN echo "export LSST_DDS_DOMAIN=auxtelpath" >> $INSTALL_PATH/setup_HeaderService.env
# --- End of HeaderService and salpytools ----

# Add $HSUSER as user
RUN useradd -ms /bin/bash $HSUSER
RUN usermod -aG wheel $HSUSER

ENV USER $HSUSER
ENV HOME /home/$HSUSER
ENV SHELL /bin/bash

USER $HSUSER
WORKDIR /home/$HSUSER
