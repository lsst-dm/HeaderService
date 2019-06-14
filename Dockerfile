# To build:
# docker build -t centos7_sal --rm=true .

# Clean up:
# docker rm $(docker ps -a -q)

# To run the HeaderService:
# > source  /opt/lsst/setup_HeaderService.env
# > DMHS_ATS_configurable  -c $HEADERSERVICE_DIR/etc/conf/atTelemetry.yaml --timeout_endTelem 600
# for help:
# > DMHS_ATS_configurable  --help

FROM centos:7

LABEL name="CentOS Base Image" \
    vendor="CentOS" \
    license="GPLv2" \
    build-date="20161214"

# Definitions
ARG FITSIO_VERSION=1.0.4
ARG SAL_VERSION=3.10.0_001
ARG OSPL_VERSION=6.9.0
ARG GIT_LSST="https://github.com/lsst-dm"
ARG INSTALL_PATH=/opt/lsst
ARG HEADERSERVICE_VERSION=0.9.7
ARG SALPYTOOLS_VERSION=0.9.7
ARG HSUSER=headerservice

RUN yum -y install https://centos7.iuscommunity.org/ius-release.rpm
RUN yum -y install python36u python36u-devel python36u-pip
RUN yum -y install python2-pip
RUN yum -y install patch
RUN yum -y install deltarpm
RUN yum -y install xterm boost-python boost-python-devel maven  python-devel java-1.7.0-openjdk-devel
RUN yum -y install epel-release
RUN yum -y install python-astropy ipython
RUN yum -y install wget
RUN yum -y install git
RUN yum -y install make
RUN yum -y install emacs
RUN yum -y install gcc-c++ gcc.x86_64 gcc-gfortran

# Pip2/3 -- once we upgrade it's renamed pip3.6 --> pip3
RUN pip install --upgrade pip
RUN pip3.6 install --upgrade pip
RUN pip3 install astropy
RUN pip3 install ipython
RUN pip3 install pyyaml
RUN pip3 install fitsio==$FITSIO_VERSION

# Make python3 link
RUN ln -s /usr/bin/python3.6 /usr/bin/python3

# ---------------------
# ts_sal rpms
# Add the lsst-ts repo
RUN wget https://raw.githubusercontent.com/menanteau/lsst_ts_install_patch/master/lsst-ts.repo -O /etc/yum.repos.d/lsst-ts.repo

RUN yum -y install OpenSpliceDDS-$OSPL_VERSION
RUN yum -y install ATHeaderService-$SAL_VERSION \
    ATCamera-$SAL_VERSION \
    ATArchiver-$SAL_VERSION \
    EFD-$SAL_VERSION \
    Scheduler-$SAL_VERSION \
    ATPtg-$SAL_VERSION \
    ATMCS-$SAL_VERSION \
    ATSpectrograph-$SAL_VERSION \
    ATTCS-$SAL_VERSION \
    # Needed by ATArchiver
    CatchupArchiver-$SAL_VERSION \
    MTArchiver-$SAL_VERSION \
    PromptProcessing-$SAL_VERSION


# Get the setup conf
RUN wget https://raw.githubusercontent.com/menanteau/lsst_ts_install_patch/master/setup_SAL.env -O /opt/lsst/setup_SAL.env
# ---------------------

# Add $HSUSER as user
RUN useradd -ms /bin/bash $HSUSER
RUN usermod -aG wheel $HSUSER

# Install HeaderService
ARG PRODUCT=HeaderService
ARG VERSION=$HEADERSERVICE_VERSION
ARG PRODUCT_DIR=$INSTALL_PATH/$PRODUCT/$VERSION
ARG INSTALL_DIR=$INSTALL_PATH/$PRODUCT/$VERSION/sandbox-install

# Create the init env file
RUN echo "source $INSTALL_PATH/setup_SAL.env" > $INSTALL_PATH/setup_HeaderService.env

# Git clone and version checkout
RUN mkdir -p $INSTALL_DIR \
    && cd $INSTALL_DIR \
    && git clone $GIT_LSST/$PRODUCT.git \
    && cd $PRODUCT \
    && git checkout $VERSION \
    && mkdir -p $PRODUCT_DIR \
    && export PYTHONPATH=$PYTHONPATH:$PRODUCT_DIR/python \
    && python3 setup.py install --prefix=$PRODUCT_DIR --install-lib=$PRODUCT_DIR/python

# Add to the init file
RUN echo "source $PRODUCT_DIR/setpath.sh $PRODUCT_DIR" >> $INSTALL_PATH/setup_HeaderService.env

# Install the salpytools
ARG PRODUCT=salpytools
ARG VERSION=$SALPYTOOLS_VERSION
ARG PRODUCT_DIR=$INSTALL_PATH/$PRODUCT/$VERSION
ARG INSTALL_DIR=$INSTALL_PATH/$PRODUCT/$VERSION/sandbox-install

# Git clone and version checkout
RUN mkdir -p $INSTALL_DIR \
    && cd $INSTALL_DIR \
    && git clone $GIT_LSST/$PRODUCT.git \
    && cd $PRODUCT \
    && git checkout $VERSION \
    && mkdir -p $PRODUCT_DIR \
    && export PYTHONPATH=$PYTHONPATH:$PRODUCT_DIR/python \
    && python3 setup.py install --prefix=$PRODUCT_DIR --install-lib=$PRODUCT_DIR/python

# Add to the init file
RUN echo "source $PRODUCT_DIR/setpath.sh $PRODUCT_DIR" >> $INSTALL_PATH/setup_HeaderService.env
RUN echo "export LSST_DDS_DOMAIN=auxtelpath" >> $INSTALL_PATH/setup_HeaderService.env

# Make /opt writable by $HSUSER
RUN chown $HSUSER:$HSUSER /opt

ENV USER $HSUSER
ENV HOME /home/$HSUSER
ENV SHELL /bin/bash

USER $HSUSER
WORKDIR /home/$HSUSER


