

# --- SEISBOX patch: numba was compiled for writable arrays only; arrays read
# from HDF5 can be read-only (e.g. event IDs in event_based landslide/secondary
# perils), which raised "No matching definition for ... readonly array(uint32)".
_seisbox_idx_start_stop = idx_start_stop


def idx_start_stop(integers):  # noqa: F811
    if hasattr(integers, "flags") and not integers.flags.writeable:
        integers = integers.copy()
    return _seisbox_idx_start_stop(integers)
