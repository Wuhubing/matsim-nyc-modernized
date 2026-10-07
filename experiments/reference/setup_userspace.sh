#!/usr/bin/env bash
# Install JDK 25 and Maven 3.9 into $TOOLS (default ~/tools) without root, for HPC clusters.
# Prints the two export lines to add to ~/.bashrc.
set -euo pipefail
TOOLS=${TOOLS:-$HOME/tools}
mkdir -p "$TOOLS" && cd "$TOOLS"
ARCH=$(uname -m); case "$ARCH" in x86_64) JA=x64;; aarch64) JA=aarch64;; *) echo "unsupported arch $ARCH"; exit 1;; esac
if [ ! -d jdk-25 ]; then
  curl -fL -o jdk25.tar.gz "https://api.adoptium.net/v3/binary/latest/25/ga/linux/${JA}/jdk/hotspot/normal/eclipse"
  mkdir jdk-25 && tar -xzf jdk25.tar.gz -C jdk-25 --strip-components=1 && rm jdk25.tar.gz
fi
if [ ! -d apache-maven-3.9.11 ]; then
  curl -fL -o maven.tar.gz https://archive.apache.org/dist/maven/maven-3/3.9.11/binaries/apache-maven-3.9.11-bin.tar.gz
  tar -xzf maven.tar.gz && rm maven.tar.gz
fi
"$TOOLS/jdk-25/bin/java" -version
"$TOOLS/apache-maven-3.9.11/bin/mvn" -version | head -1
echo
echo "Add to ~/.bashrc:"
echo "export JAVA_HOME=$TOOLS/jdk-25"
echo "export PATH=\$JAVA_HOME/bin:$TOOLS/apache-maven-3.9.11/bin:\$PATH"
