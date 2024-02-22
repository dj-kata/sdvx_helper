target="sdvx_helper"
pyin=/mnt/c/*/Python310/Scripts/pyinstaller.exe
$pyin $target.pyw --clean --noconsole --onefile --icon=icon.ico --add-data "icon.ico;./" 
cp dist/*.exe to_bin/
cp dist/*.exe $target/
rm -rfv $target/ocr_reporter.exe
rm -rfv $target/manage_score.exe
cp resources -a to_bin/
cp resources -a $target/
rm -rf out/*.xml
cp out -a to_bin/
cp out -a $target/
cp version.txt $target/
#zip $target.zip $target/* $target/*/* $target/*/*/*
rm -rf $target.zip
zip $target.zip $target/* $target/*/* 
