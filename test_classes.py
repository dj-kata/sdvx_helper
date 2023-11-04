from sdvxh_classes import *


a = SDVXLogger()
a.update_best_allfumen()
a.update_total_vf()
a.update_stats()

for i,p in enumerate(a.alllog):
    if len(p.date) != 15:
        print(p.title, p.date, len(p.date))
        #p.disp()

a.alllog.sort()

tmp = a.analyze()
print(tmp, len(tmp))

#a.gen_jacket_imgs()

#for i in range(15,20):
#    a.stats.data[i].disp()

#for f in a.best_allfumen:
#    if f.lv == 19:
#        f.disp()