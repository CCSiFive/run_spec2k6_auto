from abc import abstractclassmethod
import argparse
import os
import os.path as osp
import re
import configparser
import subprocess
import sys
import netifaces as ni
import shutil
import socket

def parse_args():
    parser = argparse.ArgumentParser(
	formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-i', '--ini',
                        required = True,
            help = '''input ini file.
should include below section/key
  [fpga]
     target =
     core = 
     bit =
  [software]
     uboot_itb = 
     uboot_spl =
     dtb =
     kernel =
''')

    parser.add_argument('--spec2k6-size',
                        type=str,
                        default="ref",
                        help="ref / train / test")
    parser.add_argument('--spec2k6-iter',
                        type=int,
                        default=1,
                        help="1 or more")
    parser.add_argument('--spec2k6-binary',
                        required = True,
                        type=lambda x: check_file_exist(parser, x),
                        help="path of spec2k6's bin")
    parser.add_argument('--spec2k6-casename',
                        required = True,
                        type=str,
                        help="462.libquantum or ...")
    
    parser.add_argument('--not-keep-nbd-when-exit',
                        action='store_true',
                        help="Exit and close the NBD")
    parser.add_argument('--not-reflash',
                        action='store_true',
                        help="Not reflash fpga again")
    
    return parser.parse_args()


def check_file_exist(parser, filename):
    err_msg = "The file {} does not exist!".format(filename)

    if not osp.exists(filename):
        if parser is None:
            ## called from normal function
            sys.exit(1)
        else:
            ## called from parse_args function
            parser.error(err_msg)
    return filename

def is_file_exist(filename):
    if not osp.exists(filename):
        print("The file {} does not exist!".format(filename))
        sys.exit(1)

    return filename

def compare_two_files(p1: str, p2: str):
    md5sum1 = ["md5sum", p1]
    process = subprocess.Popen(md5sum1, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = process.communicate()
    utf8_out = out.decode('utf-8')
    strs = utf8_out.split(" ")
    md5sum1_out = strs[0]
    
    md5sum2 = ["md5sum", p2]
    process = subprocess.Popen(md5sum2, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    out, err = process.communicate()
    utf8_out = out.decode('utf-8')
    strs = utf8_out.split(" ")
    md5sum2_out = strs[0]

    if md5sum1_out == md5sum2_out:
        return True
    else:
        return False

def parse_ini(args):
    config = configparser.ConfigParser()
    config.read(args.ini)

    try:
        args.script_dir = config.get('script', 'dir')
        is_file_exist(args.script_dir)
    except configparser.NoSectionError:
        print("Ini file parsing error")

    try:
        target = config.get('fpga', 'target')
        core = config.get('fpga', 'core')
        args.target = "{0}_{1}".format(core, target)
        args.bit = config.get('fpga', 'bit')
        is_file_exist(args.bit)
    except configparser.NoSectionError:
        print("Ini file parsing error")

    try:
        args.uboot_itb = config.get('fusdk', 'uboot_itb')
        is_file_exist(args.uboot_itb)
    except configparser.NoSectionError:
        print("Ini file parsing error")

    try:
        args.uboot_spl = config.get('fusdk', 'uboot_spl')
        is_file_exist(args.uboot_spl)
    except configparser.NoSectionError:
        print("Ini file parsing error")

    try:
        args.dtb = config.get( 'fusdk', 'dtb')
        is_file_exist(args.dtb)
    except configparser.NoSectionError:
        print("Ini file parsing error")
 
    try:
        args.kernel = config.get('fusdk', 'kernel')
        is_file_exist(args.kernel)
    except configparser.NoSectionError:
        print("Ini file parsing error")

    try:
        args.root_fs = config.get('fusdk' , 'root_fs')
        is_file_exist(args.root_fs)
    except configparser.NoSectionError:
        print("Ini file parsing error")

def get_ip_addr():
    ip = ni.ifaddresses('ethtest')[ni.AF_INET][0]['addr']
    return ip

class file_handler:
    folder_path = ""
    bit_path = ""
    uboot_itb_path = ""
    uboot_spl_path = ""
    dtb_path = ""
    kernel_path = ""
    root_fs_path = ""
    @abstractclassmethod
    def create_directory(self):
        pass
    @abstractclassmethod
    def delete_directory(self):
        pass
    @abstractclassmethod
    def create_symlink(self):
        pass
    @abstractclassmethod
    def copy_neccessary_file(self):
        pass

class preparation_handler(file_handler):
    def __init__(self, args, path: str = "./", folder_name: str = "symlink_dir"):
        self.args = args
        self.dir = osp.abspath(path)
        self.folder_name = folder_name
        self.folder_path = "{0}/{1}".format(osp.abspath(self.dir), self.folder_name)

    def is_file_exist(self, path: str):
        abs_path = osp.abspath(path)
        if osp.isfile(abs_path):
            return abs_path

        return ""
        
    def create_directory(self):
        try:
            os.makedirs(self.folder_path)
        except:
            print("Directory already exist!")
            pass

    def delete_directory(self):
        try:
            for root, dirs, files in os.walk(self.folder_path, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))

            os.rmdir(self.folder_path)
        except:
            pass  
    
    def create_symlink(self, org: str, link: str):
        try:
            os.symlink(org, link)
        except:
            if not compare_two_files(org, link):
                # remove and create new one
                os.remove(link)
                os.symlink(org, link)

    def prepare_symlinks(self):
        print("Prepare bitstream ...")
        base_name = os.path.basename(self.args.bit)
        self.bit_path = "{0}/{1}.bit".format(self.folder_path, "design-vcu118")
        self.create_symlink(self.args.bit, self.bit_path)
        
        print("Prepare uboot_spl ...")
        base_name = os.path.basename(self.args.uboot_spl)
        self.uboot_spl_path = "{0}/{1}".format(self.folder_path, base_name)
        self.create_symlink(self.args.uboot_spl, self.uboot_spl_path)
        
        print("Prepare uboot_itb ...")
        base_name = os.path.basename(self.args.uboot_itb)
        self.uboot_itb_path = "{0}/{1}".format(self.folder_path, base_name)
        self.create_symlink(self.args.uboot_itb, self.uboot_itb_path)
        
        print("Prepare kernel ...")
        base_name = os.path.basename(self.args.kernel)
        self.kernel_path = "{0}/{1}".format(self.folder_path, base_name)
        self.create_symlink(self.args.kernel, self.kernel_path)
        
        print("Prepare dtb ...")
        base_name = os.path.basename(self.args.dtb)
        self.dtb_path = "{0}/{1}".format(self.folder_path, base_name)
        self.create_symlink(self.args.dtb, self.dtb_path)
        
    def copy_neccessary_file(self):
        print("Prepare root_fs ...")
        base_name = os.path.basename(self.args.root_fs)
        self.root_fs_path = "{0}/{1}".format(self.folder_path, base_name)

        if not osp.exists(self.root_fs_path):
            shutil.copyfile(self.args.root_fs, self.root_fs_path)
        else:
            if not compare_two_files(self.args.root_fs, self.root_fs_path):
                # remove and create new one
                os.remove(self.root_fs_path)
                shutil.copyfile(self.args.root_fs, self.root_fs_path)

def run_spec2k6(args, handler: file_handler):
    script_dir = args.script_dir
    script_path = "{0}/pro_fpga_run_linux.py".format(script_dir)

    command_run_spec2k6 = ["python3", script_path, "-t", args.target,
           "-d", handler.folder_path, "--nbd",
           "--uboot-spl-path", handler.uboot_spl_path,
           "--uboot-itb-path", handler.uboot_itb_path,
           "--rootfs-path", handler.root_fs_path,
           "--kernel-path", handler.kernel_path,
           "--dtb-path", handler.dtb_path,
           "--fpga-use-static-ip",
           "--server-ip", get_ip_addr(),
           "--spec2k6",
           "--spec2k6-size", args.spec2k6_size,
           "--spec2k6-iter", str(args.spec2k6_iter),
           "--spec2k6-binary", args.spec2k6_binary,
           "--spec2k6-casename", args.spec2k6_casename,
           "--retry", str(3)]
    
    if args.not_keep_nbd_when_exit is False:
        command_run_spec2k6.append("--keep-nbd-when-exit")

    if args.not_reflash is True:
        command_run_spec2k6.append("--skip-linux-boot")
        command_run_spec2k6.append("--skip-program-fpga")

    print(command_run_spec2k6)
    subprocess.run(command_run_spec2k6)

def get_machine_name():
    host_name = socket.gethostname()
    strs = host_name.split(".")
    machine_name = strs[0]
    return machine_name

if __name__ == "__main__":
    args = parse_args()
    args.script_dir = ""
    args.bit = ""
    args.target = ""
    args.uboot_itb = ""
    args.uboot_spl = ""
    args.dtb = ""
    args.kernel = ""
    args.root_fs = ""

    parse_ini(args)

    symlink_dir = "symlink_dir_{0}".format(get_machine_name())
    handler = preparation_handler(args, folder_name=symlink_dir)

    #create directory
    handler.create_directory()
    
    #create symbolic link
    handler.prepare_symlinks()

    # copy root fs
    handler.copy_neccessary_file()
    
    run_spec2k6(args, handler)
    
    # delete directory
    # handler.delete_directory()
