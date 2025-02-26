import os
import shutil
import xml.etree.ElementTree as ET
from subprocess import run, CalledProcessError
import sys
import argparse

# 移除 OUTPUT_APK 常量，改用參數傳入
TEMP_FOLDER = 'temp_unzip'

def parse_args():
    parser = argparse.ArgumentParser(description='合併多個 APK 文件')
    parser.add_argument('apk_files', nargs='+', help='要合併的 APK 文件列表')
    parser.add_argument('-o', '--output', default='combined.apk', help='輸出的 APK 文件名稱 (預設: combined.apk)')
    return parser.parse_args()

def print_usage():
    print("用法: python merge.py [APK檔案1] [APK檔案2] ... [-o output.apk]")
    print("例如: python merge.py base.apk split_assetpack.apk split_config.arm64_v8a.apk -o combined.apk")
    sys.exit(1)

# 解包 APK
def decompile_apk(apk_path, output_folder):
    print(f"解包 APK: {apk_path}")
    run(f"apktool d {apk_path} -o {output_folder}", shell=True, check=True)

# 合併 AndroidManifest.xml
def merge_manifests(base_manifest, split_manifests):
    base_tree = ET.parse(base_manifest)
    base_root = base_tree.getroot()

    for split_manifest in split_manifests:
        split_tree = ET.parse(split_manifest)
        split_root = split_tree.getroot()

        # 合併權限、活動等
        merge_permissions(base_root, split_root)
        merge_activities(base_root, split_root)
        merge_services(base_root, split_root)

    # 移除 Split APK 相關配置
    remove_split_apk_configs(base_root)

    # 儲存合併後的 AndroidManifest.xml
    base_tree.write(f'{TEMP_FOLDER}/base/AndroidManifest.xml')

# 合併權限
def merge_permissions(base_root, split_root):
    base_permissions = base_root.findall('uses-permission')
    split_permissions = split_root.findall('uses-permission')

    for perm in split_permissions:
        if perm not in base_permissions:
            base_root.append(perm)

# 合併活動
def merge_activities(base_root, split_root):
    base_activities = base_root.findall('application/activity')
    split_activities = split_root.findall('application/activity')

    for activity in split_activities:
        if activity not in base_activities:
            base_root.find('application').append(activity)

# 合併服務
def merge_services(base_root, split_root):
    base_services = base_root.findall('application/service')
    split_services = split_root.findall('application/service')

    for service in split_services:
        if service not in base_services:
            base_root.find('application').append(service)

# 移除 Split APK 相關配置
def remove_split_apk_configs(manifest_root):
    print("移除 Split APK 相關配置...")
    
    # 移除 manifest 元素中的所有 split 相關屬性
    for attr in manifest_root.attrib.copy():
        if any(split_keyword in attr.lower() for split_keyword in ['split', 'base__abi']):
            del manifest_root.attrib[attr]

# 合併資源
def merge_resources(base_folder, split_folders):
    for folder in split_folders:
        # 如果資料夾存在，則繼續處理
        if os.path.exists(folder):
            for item in os.listdir(folder):
                src_path = os.path.join(folder, item)
                dst_path = os.path.join(base_folder, item)

                if os.path.isdir(src_path):
                    # 如果目標資料夾不存在，則創建它
                    if not os.path.exists(dst_path):
                        os.makedirs(dst_path)
                    merge_resources(dst_path, [src_path])
                else:
                    # 如果資料夾不存在，也會自動創建
                    if not os.path.exists(os.path.dirname(dst_path)):
                        os.makedirs(os.path.dirname(dst_path))
                    shutil.copy(src_path, dst_path)
        else:
            print(f"警告: 資料夾 {folder} 不存在，跳過此資料夾。")

# 合併 APK
def merge_apks(apk_files, output_apk):
    if not apk_files:
        print_usage()
        return

    # 建立臨時資料夾
    if not os.path.exists(TEMP_FOLDER):
        os.makedirs(TEMP_FOLDER)

    if os.path.isfile(output_apk):
        os.remove(output_apk)

    # 解包第一個 APK 作為基礎
    print(f"解包基礎 APK: {apk_files[0]}...")
    decompile_apk(apk_files[0], f'{TEMP_FOLDER}/base')

    # 解包其餘的 APK
    split_manifests = []
    for i, apk in enumerate(apk_files[1:], 1):
        print(f"解包 APK {i+1}: {apk}...")
        output_folder = f'{TEMP_FOLDER}/split_{i}'
        decompile_apk(apk, output_folder)
        split_manifests.append(f'{output_folder}/AndroidManifest.xml')

    # 合併 AndroidManifest.xml
    print("合併 AndroidManifest.xml...")
    merge_manifests(
        f'{TEMP_FOLDER}/base/AndroidManifest.xml',
        split_manifests
    )

    # 合併資源和其他檔案
    print("合併資源檔案...")
    for i in range(1, len(apk_files)):
        split_folder = f'{TEMP_FOLDER}/split_{i}'
        merge_resources(f'{TEMP_FOLDER}/base/res', [f'{split_folder}/res'])
        merge_resources(f'{TEMP_FOLDER}/base/lib', [f'{split_folder}/lib'])
        merge_resources(f'{TEMP_FOLDER}/base/assets', [f'{split_folder}/assets'])

    # 重新編譯 APK
    print("重新編譯 APK...")
    run(f"apktool b {TEMP_FOLDER}/base -o {output_apk}", shell=True, check=True)

    # 清理臨時資料夾
    print("清理臨時資料夾...")
    shutil.rmtree(TEMP_FOLDER)

    print(f"合併完成！生成的 APK: {output_apk}")

    # 添加 zipalign 對齊優化
    print("執行 zipalign 對齊優化...")
    aligned_apk = f"{os.path.splitext(output_apk)[0]}-align.apk"
    if os.path.isfile(aligned_apk):
        os.remove(aligned_apk)

    try:
        run(f"zipalign -v -p 4 {output_apk} {aligned_apk}", shell=True, check=True)
    except CalledProcessError:
        print("警告: zipalign 失敗，請確認是否已安裝 Android SDK build tools")
        return

    # 生成金鑰庫（如果不存在）
    if not os.path.exists("my-release-key.jks"):
        print("生成簽名金鑰...")
        try:
            run('keytool -genkey -v -keystore my-release-key.jks -keyalg RSA -keysize 2048 -validity 10000 -alias my-alias -storepass 123456 -keypass 123456 -dname "CN=Unknown, OU=Unknown, O=Unknown, L=Unknown, ST=Unknown, C=Unknown"', shell=True, check=True)
        except CalledProcessError:
            print("警告: 金鑰生成失敗，請確認是否已安裝 Java")
            return

    # 簽署 APK
    print("簽署 APK...")
    try:
        run(f"apksigner sign --ks my-release-key.jks --ks-pass pass:123456 --out {output_apk} {aligned_apk}", shell=True, check=True)
        print(f"完成！最終 APK: {output_apk}")
    except CalledProcessError:
        print("警告: APK 簽署失敗，請確認是否已安裝 Android SDK build tools")
        return
    finally:
        # 清理臨時文件
        cleanup_temp_files(output_apk, aligned_apk)

def cleanup_temp_files(output_apk, aligned_apk):
    """清理運行期間產生的臨時文件"""
    print("清理臨時文件...")
    temp_files = [
        aligned_apk,
        f"{output_apk}.idsig",
        'my-release-key.jks'
    ]
    for file in temp_files:
        if os.path.exists(file):
            try:
                os.remove(file)
                print(f"已刪除: {file}")
            except Exception as e:
                print(f"無法刪除 {file}: {e}")

# 主程式
if __name__ == "__main__":
    args = parse_args()
    
    # 檢查所有檔案是否存在
    for apk in args.apk_files:
        if not os.path.exists(apk):
            print(f"錯誤: 找不到檔案 {apk}")
            sys.exit(1)
    
    merge_apks(args.apk_files, args.output)
