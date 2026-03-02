from src.config_dialog import _AlllogUnpickler


with open('debug/alllog.pkl', 'rb') as f:
    data = _AlllogUnpickler(f).load()

# target=[]
# for i,item in enumerate(data):
#     if getattr(item, 'cur_score') == 0:
#         target.append(i)


for i,item in enumerate(data):
    if getattr(item, 'title') == '月光乱舞' and getattr(item, 'difficulty')=='APPEND':
        print(getattr(item, 'cur_score'),getattr(item, 'lamp'))

# for t in reversed(target):
#     data.pop(t)

# import pickle
# with open('debug/alllog.pkl', 'wb') as f:
#     pickle.dump(data, f)