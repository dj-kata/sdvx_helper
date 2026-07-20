-include ../.env

WUV ?= $(wuv)

ifeq ($(strip $(WUV)),)
$(error WUV is not set. Copy ../.env.sample to ../.env and set WUV=/mnt/c/Users/<user>/.local/bin/uv.exe)
endif

outdir=update
target=$(outdir)/update.exe
srcs=$(subst update.py,,$(wildcard *.py)) $(wildcard *.pyw)
html_files=$(wildcard html/*.*)

all: $(target)

$(target): $(srcs)
	@$(WUV) run pyarmor -d gen --output=$(outdir) --pack onefile otoge_input_viewer.pyw
$(outdir)/update.exe: update.py
	@$(WUV) run pyarmor -d gen --output=$(outdir) --pack onefile $<

dist: 
	@cp -a html to_bin/
	@cp -a version.txt to_bin/
	@cp -a $(outdir)/*.exe to_bin/

clean:
	@rm -rf $(target)
	@rm -rf $(outdir)/update.exe
	@rm -rf __pycache__
	@rm -rf pyarmor*log

test:
	@$(WUV) run update.py
