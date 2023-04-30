cmake \
	-DCMAKE_EXPORT_COMPILE_COMMANDS=ON \
	-DCMAKE_INSTALL_PREFIX="$WORKSPACE"/usr \
	-DCMAKE_BUILD_TYPE=Debug \
	-S . \
	-B ./build \
	-G Ninja &&
	ninja -C ./build &&
	ninja -C ./build install
