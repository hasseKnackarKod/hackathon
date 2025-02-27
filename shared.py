from multiprocessing import Manager

manager = Manager()
shared_data = manager.dict()  # Shared dictionary accessible live
shared_data['df'] = None
shared_data['df_daily'] = None
