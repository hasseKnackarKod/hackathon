from multiprocessing import Manager

def get_shared_data():
    """Creates a shared dictionary using multiprocessing Manager."""
    manager = Manager()
    shared_data = manager.dict()  # Shared dictionary accessible live
    shared_data["df"] = None  # Initialize shared dataframe
    shared_data["df_daily"] = None
    return shared_data

# Do NOT create shared_data at import time!
shared_data = None  
