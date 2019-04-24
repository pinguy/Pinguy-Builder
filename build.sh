#!/usr/bin/env bash

VERSION=$(awk -F: '$1~/Version/{gsub(/ /, "", $2);;print $2}' src/DEBIAN/control)

chmod 775 src/DEBIAN/preinst
chmod 775 src/DEBIAN/postinst
chmod 775 src/DEBIAN/prerm
chmod 775 src/DEBIAN/postrm

rm src/DEBIAN/md5sums
find src -path "src/DEBIAN" -prune -o -type f -print0 | xargs -0 md5sum | sed 's/ src/ /g' >> src/DEBIAN/md5sums

fakeroot dpkg -b src pinguybuilder_${VERSION}_all.deb

if [[ $1=="tag" && -z $(git tag -l "$VERSION") ]]; then
    echo tagging version ${VERSION}
    git tag -s $VERSION -m "Version ${VESRION}"
else
    echo "This version is already tagged"
fi


