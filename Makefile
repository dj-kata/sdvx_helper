wuv=/mnt/c/Users/katao/.local/bin/uv.exe
main_file_name=sdvx_helper
project_name=sdvx_helper
target=$(project_name)/.built  # timestampファイルにすることで連続でmakeできないように対策
target_zip=$(project_name).zip
srcs=$(wildcard *.py) $(wildcard *.pyw) $(wildcard src/*.py) $(wildcard misc/*.py)
html_files=$(wildcard template/*.html)
version=$(shell head -n1 version.txt)
ZIP ?= 7z a -tzip -mx=1 -mmt=on

# all: $(target_zip)
top: $(target)
all: $(target_zip)

$(target_zip): $(target) $(html_files) version.txt
	@rm -rf $(target_zip)
	@cp version.txt $(project_name)
	@cp -a template $(project_name)
	@mkdir -p $(project_name)/infnotebook
	@cp -a infnotebook/resources $(project_name)/infnotebook/
	@rm -rf $(project_name)/log
	@rm -rf $(project_name)/*.json
	@$(ZIP) $(target_zip) $(project_name)

$(target): $(srcs)
	@rm -rf $(project_name)
	@$(wuv) run setup.py build
	@echo "不要なファイルを削除中..."

# 	# Tcl/Tk関連
# 	@rm -rf $(project_name)/share/tcl8.6/tzdata
# 	@rm -rf $(project_name)/share/tcl8.6/msgs
# 	@rm -rf $(project_name)/share/tk8.6/msgs
# 	@rm -rf $(project_name)/share/tcl8.6/encoding  # ASCIIとUTF-8以外不要なら
# 	# Qt DLL
	@rm -f $(project_name)/lib/PySide6/Qt6WebEngine*.dll 2>/dev/null || true

# 	# Python関連
# 	@find $(project_name) -name "*.pyc" -delete
# 	@find $(project_name) -name "__pycache__" -type d -delete
# 	@find $(project_name) -name "*.pyo" -delete
# 	# テスト/ドキュメント
# 	@find $(project_name) -type d -name "test" -exec rm -rf {} + 2>/dev/null || true
# 	@find $(project_name) -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
	@touch $(target)

dist: 
	@cp -a html to_bin/
	@cp -a version.txt to_bin/
	@cp -a $(project_name)/*.exe to_bin/

clean:
	@rm -rf $(target)
	@rm -rf __pycache__

test:
	@$(wuv) run python $(main_file_name).pyw
