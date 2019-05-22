#!/usr/bin/env python
# -*- coding: UTF-8 -*-

# Licence: GPLv3.0
# Copyright: Krasimir S. Stefanov <lokiisyourmaster@gmail.com>
# Modified by: Tony Brijeski <tb6517@yahoo.com>
# Modified by: Pablo González <pablodgonzalez@gmail.com>

try:
    import sys
    import traceback
    import os
    import os.path
    import stat
    import locale
    import gettext
    import gi
    gi.require_version('Vte', '2.91')
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk, Vte, GLib
    import re
    import shutil
    import datetime
    import time
    import subprocess
    import shlex
    import ConfigParser

except Exception as detail:
    print "Please install all dependencies!", detail
    print '-' * 60
    traceback.print_exc(file=sys.stdout)
    print '-' * 60
    sys.exit(1)

APP = "PinguyBuilder-gtk"
DIR = "/usr/share/locale"
APP_VERSION = "5.2-1"

locale.setlocale(locale.LC_ALL, '')

gettext.bindtextdomain(APP, DIR)
gettext.textdomain(APP)
_ = gettext.gettext

LOCALE = locale.getlocale()[0]


class Appgui:
    def __init__(self):
        self.pathname = os.path.dirname(sys.argv[0])
        self.abspath = os.path.abspath(self.pathname)
        self.filepath = os.path.dirname(__file__)
        self.conffile = os.path.join(self.filepath, "../../../../../etc/PinguyBuilder.conf")
        self.gladefile = os.path.join(self.filepath, "../../../../share/PinguyBuilder-gtk/ui/PinguyBuilder-gtk.glade")
        self.builder = Gtk.Builder()
        self.builder.set_translation_domain()
        self.builder.add_from_file(self.gladefile)
        handlers = {
            "on_button_backup_clicked": self.on_button_backup_clicked,
            "on_button_dist_clicked": self.on_button_dist_clicked,
            "on_button_distISO_clicked": self.on_button_distISO_clicked,
            "on_button_distfs_clicked": self.on_button_distfs_clicked,
            "on_button_clear_clicked": self.on_button_clear_clicked,
            "on_button_boot_picture_livecd_clicked": self.on_button_boot_picture_livecd_clicked,
            "on_button_boot_picture_installed_clicked": self.on_button_boot_picture_installed_clicked,
            "on_button_user_skel_clicked": self.on_button_user_skel_clicked,
            "on_button_delete_skel_clicked": self.on_button_delete_skel_clicked,
            "on_button_plymouth_theme_clicked": self.on_button_plymouth_theme_clicked,
            "on_button_working_directory_clicked": self.on_button_working_directory_clicked,
            "on_button_about_clicked": self.on_button_about_clicked,
            "on_button_close_clicked": self.quit,
            "on_window_main_delete_event": self.quit,
            "destroy": Gtk.main_quit,
            "on_window_plymouth_delete_event": self.on_button_window_plymouth_cancel_clicked,
            "on_button_window_plymouth_cancel_clicked": self.on_button_window_plymouth_cancel_clicked,
            "on_button_window_plymouth_ok_clicked": self.on_button_window_plymouth_ok_clicked,
            "on_button_window_plymouth_create_clicked": self.on_button_window_plymouth_create_clicked,
            "on_button_window_plymouth_preview_clicked": self.on_button_window_plymouth_preview_clicked,
            "on_checkbutton_window_plymouth_auto_toggled": self.on_checkbutton_window_plymouth_auto_toggled,
            "on_window_user_skeleton_delete_event": self.on_button_window_user_skeleton_cancel_clicked,
            "on_button_window_user_skeleton_cancel_clicked": self.on_button_window_user_skeleton_cancel_clicked,
            "on_button_window_user_skeleton_ok_clicked": self.on_button_window_user_skeleton_ok_clicked

        }
        self.builder.connect_signals(handlers)
        self.window_main = self.builder.get_object("window_main")
        self.working_dir = os.path.expanduser("~")
        self.callback_id = 0

        self.v = Vte.Terminal()
        self.v.set_hexpand(True)
        self.builder.get_object("grid_output").add(self.v)
        self.v.show()
        self.load_settings()
        msg_info(_("It is necessary to close all other windows and unmount any network shares while running "
                   "PinguyBuilder Backup. Please do so now and then click OK when you are ready to continue."),
                 self.window_main)

        # Setup Plymouth selector window layout
        _nameColumn = Gtk.TreeViewColumn(_('Name'))
        _plymouthPathColumn = Gtk.TreeViewColumn(_('Directory'))

        _nameCell = Gtk.CellRendererText()
        _plymouthCell = Gtk.CellRendererText()
        _nameColumn.pack_start(_nameCell, True)
        _plymouthPathColumn.pack_start(_plymouthCell, True)
        _nameColumn.set_attributes(_nameCell, text=0)
        _plymouthPathColumn.set_attributes(_plymouthCell, text=1)

        self.builder.get_object("treeview_themes").append_column(_nameColumn)
        self.builder.get_object("treeview_themes").append_column(_plymouthPathColumn)

        #Setup Skel selector window layout
        _userColumn = Gtk.TreeViewColumn(_('User'))
        _homePathColumn = Gtk.TreeViewColumn(_('Home directory'))

        _userCell = Gtk.CellRendererText()
        _homeCell = Gtk.CellRendererText()

        _userColumn.pack_start(_userCell, True)
        _homePathColumn.pack_start(_homeCell, True)
        _userColumn.set_attributes(_userCell, text=0)
        _homePathColumn.set_attributes(_homeCell, text=1)

        self.builder.get_object("treeview_user_skeleton").append_column(_userColumn)
        self.builder.get_object("treeview_user_skeleton").append_column(_homePathColumn)
        
    def run_command(self, cmd, done_callback):
        argv = shlex.split(cmd)
        pty = Vte.Pty.new_sync(Vte.PtyFlags.DEFAULT)
        self.v.set_pty(pty)
        self.callback_id = self.v.connect("child-exited", done_callback)
        self.v.spawn_sync(Vte.PtyFlags.DEFAULT, None, argv, None,
                          GLib.SpawnFlags.SEARCH_PATH_FROM_ENVP, None, None, None)
        # self.v.feed_child('set -e\n')
        self.builder.get_object("notebook_window_main").set_current_page(2)
        self.v.show()
        # self.v.feed_child(cmd+'\nexit 0\n')

    def on_button_backup_clicked(self, widget):
        self.update_conf()
        if not msg_confirm(_("You have selected Backup Mode. Do not interrupt this process. Click OK to Start the "
                             "Backup LiveCD/DVD process."), self.window_main):
            return
        self.run_command('PinguyBuilder backup', self.on_backup_done)

    def on_backup_done(self, terminal, status):
        if status == 0:
            WORKDIR = self.builder.get_object("entry_working_directory").get_text()
            CUSTOMISO = self.builder.get_object("entry_filename").get_text()
            msg_info(_("Your %(iso)s and %(iso)s.md5 files are ready in %(dir)s. It is recommended to test it in a "
                       "virtual machine or on a rewritable cd/dvd to ensure it works as desired. Click on OK to "
                       "return to the main menu.")
                    % ({"iso": CUSTOMISO, "dir": WORKDIR+'/PinguyBuilder'}), self.window_main)
        else:
            msg_error(_("The process was interrupted!"), self.window_main)
        self.builder.get_object("notebook_window_main").set_current_page(0)
        self.v.handler_disconnect(self.callback_id)

    def on_button_dist_clicked(self, widget):
        self.update_conf()
        if not msg_confirm(_("You have selected Dist Mode. Click OK to Start the Distributable LiveCD/DVD process."),
                           self.window_main):
            return
        self.run_command('PinguyBuilder dist', self.on_dist_done)

    def on_dist_done(self, terminal, status):
        if status == 0:
            WORKDIR = self.builder.get_object("entry_working_directory").get_text()
            CUSTOMISO = self.builder.get_object("entry_filename").get_text()
            msg_info(_("Your %(iso)s and %(iso)s.md5 files are ready in %(dir)s. It is recommended to test it in a "
                       "virtual machine or on a rewritable cd/dvd to ensure it works as desired. Click on OK to "
                       "return to the main menu.") % ({"iso" : CUSTOMISO, "dir" : WORKDIR+'/PinguyBuilder'}),
                     self.window_main)
        else:
            msg_error(_("The process was interrupted!"), self.window_main)
        self.builder.get_object("notebook_window_main").set_current_page(0)
        self.v.handler_disconnect(self.callback_id)
        
    def on_button_distfs_clicked(self, widget):
        self.update_conf()
        if not msg_confirm(_("You have selected Dist CDFS Mode. Click OK to Start the Distributable LiveCD/DVD "
                             "filesystem build process."), self.window_main):
            return
        self.run_command('PinguyBuilder dist cdfs', self.on_dist_cdfs_done)

    def on_dist_cdfs_done(self, terminal, status):
        if status == 0:
            WORKDIR = self.builder.get_object("entry_working_directory").get_text()
            CUSTOMISO = self.builder.get_object("entry_filename").get_text()
            msg_info(_("Your livecd filesystem is ready in %s. You can now add files to the cd and then run the "
                       "Distiso option when you are done. Click on OK to return to the main menu.") %
                     WORKDIR+'/PinguyBuilder', self.window_main)
        else:
            msg_error(_("The process was interrupted!"), self.window_main)
        self.builder.get_object("notebook_window_main").set_current_page(0)
        self.v.handler_disconnect(self.callback_id)
    
    def on_button_distISO_clicked(self,widget):
        self.update_conf()
        WORKDIR = self.builder.get_object("entry_working_directory").get_text()
        if os.path.exists(WORKDIR+'/PinguyBuilder/ISOTMP/casper/filesystem.squashfs'):
            if not msg_confirm(_("You have selected Dist ISO Mode. Click OK to create the iso file."),
                               self.window_main):
                self.builder.get_object("window_main").show()
                return
            self.run_command('PinguyBuilder dist iso', self.on_dist_iso_done)
        else:
            msg_error(_("The livecd filesystem does not exist. Click OK to go back to the main menu and try the "
                        "normal Dist mode or the Dist CDFS again."), self.window_main)

    def on_dist_iso_done(self, terminal, status):
        if status == 0:
            WORKDIR = self.builder.get_object("entry_working_directory").get_text()
            CUSTOMISO = self.builder.get_object("entry_filename").get_text()
            msg_info(_("Your %(iso)s and %(iso)s.md5 files are ready in %(dir)s. It is recommended to test it in a "
                       "virtual machine or on a rewritable cd/dvd to ensure it works as desired. Click on OK to "
                       "return to the main menu.") % ({"iso" : CUSTOMISO, "dir" : WORKDIR+'/PinguyBuilder'}),
                     self.window_main)
        else:
            msg_error(_("The process was interrupted!"), self.window_main)
        self.builder.get_object("notebook_window_main").set_current_page(0)
        self.v.handler_disconnect(self.callback_id)
        
    def on_button_clear_clicked(self,widget):
        self.update_conf()
        if not msg_confirm(_("This will remove all the files from the temporary directory. Click OK to proceed."),
                           self.window_main):
            return
        # os.system('PinguyBuilder clean')
        self.run_command('PinguyBuilder clean', self.on_clean_done)
        # msg_info(_("Completed. Click OK to return to the main menu."), self.window_main)

    def on_clean_done(self, terminal, status):
        if status == 0:
            msg_info(_("Completed. Click OK to return to the main menu."), self.window_main)
        else:
            msg_error(_("The process was interrupted!"), self.window_main)
        self.builder.get_object("notebook_window_main").set_current_page(0)
        self.v.handler_disconnect(self.callback_id)
        
    def on_button_about_clicked(self, widget):
        # show about dialog
        about = Gtk.AboutDialog()
        about.set_transient_for(self.window_main)
        about.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
        about.set_program_name(_("PinguyBuilder"))
        about.set_version(APP_VERSION)
        about.set_authors([_("Antoni Norman <antoni.norman@gmail.com>"),
                           _("Krasimir S. Stefanov <lokiisyourmaster@gmail.com>"),
                           _("Tony Brijeski <tb6517@yahoo.com>"),
                           _("Pablo González <pablodgonzalez@gmail.com>")])
        about.set_website("http://pinguyos.com/")
        translators = [
            _("Bulgarian - Krasimir S. Stefanov <lokiisyourmaster@gmail.com>"),
            _("English - Krasimir S. Stefanov <lokiisyourmaster@gmail.com>"),
            _("Traditional Chinese - Kent Chang <kentxchang@gmail.com>"),
            _('Simplified Chinese - Mutse Young <yyhoo2.young@gmail.com>')
        ]

        about.set_translator_credits('\n'.join(translators))
        about.set_logo_icon_name('PinguyBuilder-gtk')
        license = _('''PyGTK GUI for PinguyBuilder
Copyright (C) 2018 Antoni Norman, Krasimir S. Stefanov, Tony Brijeski
Licence: DBAD
https://www.dbad-license.org/.''')
        about.set_license(license)
        about.run()
        about.hide()

    def on_button_working_directory_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(_("Select working directory"),
                                       None,
                                       Gtk.FileChooserAction.SELECT_FOLDER,
                                       (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN, Gtk.ResponseType.OK))

        dialog.set_transient_for(self.window_main)
        dialog.set_default_response(Gtk.ResponseType.OK)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.builder.get_object("entry_working_directory").set_text(dialog.get_filename())
        dialog.destroy()

    def on_button_boot_picture_livecd_clicked(self, widget):
        dialog = Gtk.FileChooserDialog( title=_("Select 640x480 PNG image..."),
                                        action=Gtk.FileChooserAction.OPEN,
                                        buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL,
                                                 Gtk.STOCK_OPEN, Gtk.ResponseType.OK))
        dialog.set_transient_for(self.window_main)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_current_folder(self.working_dir)
        
        filter = Gtk.FileFilter()
        filter.set_name(_("PNG Images"))
        filter.add_mime_type("image/png")
        dialog.add_filter(filter)

        filter = Gtk.FileFilter()
        filter.set_name(_("All files"))
        filter.add_pattern("*")
        dialog.add_filter(filter)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            now = datetime.datetime.now()
            filename = dialog.get_filename()
            dialog.destroy()  
            self.working_dir = os.path.dirname(filename)
            shutil.move("/etc/PinguyBuilder/isolinux/splash.png",
                        "/etc/PinguyBuilder/isolinux/splash.png." + now.strftime("%Y%m%d%H%M%S"))
            shutil.copy(filename, "/etc/PinguyBuilder/isolinux/splash.png")
            msg_info(_("%s has been copied to /etc/PinguyBuilder/isolinux/splash.png becoming the default background "
                       "for the LIVE menu.") % filename, self.window_main)
        else:
            dialog.destroy()                  

    def on_button_boot_picture_installed_clicked(self, widget):
        dialog = Gtk.FileChooserDialog(title=_("Select image..."),
                                       action=Gtk.FileChooserAction.OPEN,
                                       buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN,
                                                Gtk.ResponseType.OK))
        dialog.set_transient_for(self.window_main)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_current_folder(self.working_dir)
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            now = datetime.datetime.now()
            filename = dialog.get_filename()
            self.working_dir = os.path.dirname(filename)
            name, ext = os.path.splitext(filename)
            grub_bg = "/etc/PinguyBuilder/grub" + ext
            shutil.copy(filename, grub_bg)
            dialog.destroy()

            grub = open('/etc/PinguyBuilder/grub.ucf-dist').read()
            
            m = re.search('(#?)GRUB_BACKGROUND=.*', grub)
            if m is not None:
                grub.replace(m.group(0), 'GRUB_BACKGROUND="%s"' % grub_bg)
            else:
                grub += '\nGRUB_BACKGROUND="%s"' % grub_bg
            
            f = open('/etc/PinguyBuilder/grub.ucf-dist', 'w+')
            f.write(grub)
            f.close()
            
            msg_info(_("%(filename)s has been copied to %(grub_bg)s and is the default background for grub. Click OK "
                       "to update grub with the new settings so you can see your picture on the next boot.") % ({
                     'filename': filename, 'grub_bg': grub_bg}), self.window_main)
            self.builder.get_object("label_boot_picture_installed").hide()
            self.builder.get_object("progressbar_boot_picture_installed").show()
            process = subprocess.Popen(['update-grub'], stdout=subprocess.PIPE, stderr=None)
            while process.poll() is None:
                while Gtk.events_pending():
                    Gtk.main_iteration_do(False)
                time.sleep(.1) 
                self.builder.get_object("progressbar_boot_picture_installed").pulse()
            process.wait()
            self.builder.get_object("progressbar_boot_picture_installed").hide()
            self.builder.get_object("label_boot_picture_installed").show()
            msg_info(_("GRUB has been updated."), self.window_main)
        else:
            dialog.destroy()

    # BEGIN USER SKELETON HANDLERS
    def on_button_user_skel_clicked(self, widget):
        self.builder.get_object("window_main").hide()

        _liststore = Gtk.ListStore(str, str)
        self.builder.get_object("treeview_user_skeleton").set_model(_liststore)

        passwd = open('/etc/passwd', 'r').read().strip().split('\n')
        for row in passwd:
            data = row.split(':')
            if 1000 <= int(data[2]) <= 1100:
                _liststore.append([data[0], data[5]])
        self.builder.get_object("window_user_skeleton").show()

    def on_button_delete_skel_clicked(self, widget):
        if msg_confirm(_("Are you sure you want to delete the contents of /etc/skel?"), self.window_main):
            shutil.rmtree('/etc/skel/')
            os.makedirs('/etc/skel/')

    def on_button_window_user_skeleton_cancel_clicked(self, widget):
        self.builder.get_object("window_user_skeleton").hide()
        self.builder.get_object("window_main").show()

    def on_button_window_user_skeleton_ok_clicked(self, widget):
        model, treeiter = self.builder.get_object("treeview_user_skeleton").get_selection().get_selected()
        username = model.get(treeiter, 0)[0]
        self.builder.get_object("progressbar_user_skeleton").show()
        self.builder.get_object("buttonbox_user_skeleton").set_sensitive(False)
        process = subprocess.Popen(['PinguyBuilder-skelcopy', username], stdout=subprocess.PIPE, stderr=None)
        while process.poll() is None:
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            time.sleep(.1)
            self.builder.get_object("progressbar_user_skeleton").pulse()
        process.wait()
        self.builder.get_object("progressbar_user_skeleton").hide()
        self.builder.get_object("buttonbox_user_skeleton").set_sensitive(True)
        self.builder.get_object("window_user_skeleton").hide()
        self.builder.get_object("window_main").show()

    # END USER SKELETON HANDLERS

    # BEGIN PLAYMOUTH HANDLERS
    def on_button_plymouth_theme_clicked(self, widget):
        self.builder.get_object("window_main").hide()

        self._liststore = Gtk.ListStore(str, str)
        self.builder.get_object("treeview_themes").set_model(self._liststore)
        self.list_themes()
        self.builder.get_object("window_plymouth").show()

    def update_initramfs(self):
        self.builder.get_object("progressbar_plymouth").show()
        self.builder.get_object("buttonbox_plymouth").set_sensitive(False)
        uname = os.popen('uname -r').read().strip()
        process = subprocess.Popen(['mkinitramfs', '-o', '/boot/initrd.img-' + uname, uname], stdout=subprocess.PIPE,
                                   stderr=None)
        while process.poll() is None:
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            time.sleep(.1)
            self.builder.get_object("progressbar_plymouth").pulse()
        process.wait()
        self.builder.get_object("progressbar_plymouth").hide()
        self.builder.get_object("buttonbox_plymouth").set_sensitive(True)

    def list_themes(self):
        self._liststore.clear()
        output = os.popen('update-alternatives --display default.plymouth').read().strip()
        m = re.search(_('default.plymouth - (manual|auto) mode'), output)
        if m is None:
            self.builder.get_object("window_plymouth").show()
            return
        mode = m.group(1)
        m = re.search(_('link\s*currently\s*points\s*to\s*(.*)'), output)
        if m == None:
            self.builder.get_object("window_plymouth").show()
            return
        link = m.group(1).strip()
        lines = os.popen('update-alternatives --list default.plymouth').read().strip().split('\n')
        for row in lines:
            if row != "":
                config = ConfigParser.ConfigParser()
                config.readfp(open(row))
                name = config.get('Plymouth Theme', 'Name')
                iter = self._liststore.append([name, row])
                if mode == _('manual') and row == link:
                    self.builder.get_object("treeview_themes").get_selection().select_iter(iter)
        self.builder.get_object("checkbutton_window_plymouth_auto").set_active(mode == _('auto'))

    def on_checkbutton_window_plymouth_auto_toggled(self, widget):
        active = self.builder.get_object("checkbutton_window_plymouth_auto").get_active()
        self.builder.get_object("treeview_themes").set_sensitive(not active)

    def on_button_window_plymouth_preview_clicked(self, widget):

        output = os.popen('update-alternatives --display default.plymouth').read().strip()
        m = re.search(_('default.plymouth - (manual|auto) mode'), output)
        if m is None:
            self.builder.get_object("window_plymouth").show()
            return
        mode = m.group(1)

        if mode == _('auto'):
            self.builder.get_object("window_plymouth").hide()
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            os.system("plymouth-preview")
            self.builder.get_object("window_plymouth").show()
        else:
            model, treeiter = self.builder.get_object("treeview_themes").get_selection().get_selected()
            if treeiter == None:
                msg_error(_("Please, select a theme!"), self.window_main)
                return
            theme = model.get(treeiter, 1)[0]
            self.builder.get_object("window_plymouth").hide()
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)

            output = os.popen('update-alternatives --display default.plymouth').read().strip()
            m = re.search(_('default.plymouth - (manual|auto) mode'), output)
            if m == None:
                self.builder.get_object("window_plymouth").show()
                return
            mode = m.group(1)

            m = re.search(_('link\s*currently\s*points\s*to\s*(.*)'), output)
            if m == None:
                self.builder.get_object("window_plymouth").show()
                return
            link = m.group(1)

            os.system('update-alternatives --set default.plymouth "%s"' % theme)
            os.system("plymouth-preview")
            self.builder.get_object("window_plymouth").show()

            if mode == _('auto'):
                os.system('update-alternatives --auto default.plymouth')
            else:
                os.system('update-alternatives --set default.plymouth "%s"' % link)

    def on_button_window_plymouth_create_clicked(self, widget):
        theme_name = msg_input('', _(
            'Enter your plymouth theme name. eg. PinguyBuilder Theme (please use only alphanumeric characters)'),
                               _('Name:'), 'PinguyBuilder Theme', self.window_main)
        if theme_name is False or theme_name is None:
            return
        elif theme_name == '':
            msg_error(_("You must specify theme name!"), self.window_main)
            return

        theme_name_fixed = theme_name.replace(' ', '-').replace('/', '-').replace('..', '-').replace('\\', '-')
        theme_dir = "/lib/plymouth/themes/" + theme_name_fixed

        if os.path.exists(theme_dir):
            overwrite = msg_confirm(_('The theme "%s" already exists! Do you want to overwrite it?') % theme_name,
                                    self.window_main)
            if overwrite:
                shutil.rmtree(theme_dir)
            else:
                return

        dialog = Gtk.FileChooserDialog(title=_("Select 1920x1080 PNG image..."), action=Gtk.FileChooserAction.OPEN,
                                       buttons=(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OPEN,
                                                Gtk.ResponseType.OK))
        dialog.set_transient_for(self.window_main)
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.set_current_folder(self.working_dir)

        filter = Gtk.FileFilter()
        filter.set_name(_("PNG Images"))
        filter.add_mime_type("image/png")
        dialog.add_filter(filter)

        filter = Gtk.FileFilter()
        filter.set_name(_("All files"))
        filter.add_pattern("*")
        dialog.add_filter(filter)

        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            filename = dialog.get_filename()
            self.working_dir = os.path.dirname(filename)
            dialog.destroy()
            while Gtk.events_pending():
                Gtk.main_iteration_do(False)
            os.makedirs(theme_dir)
            now = datetime.datetime.now()
            theme_pic = os.path.join(theme_dir, os.path.basename(filename))
            shutil.copy(filename, theme_pic)
            shutil.copy('/etc/PinguyBuilder/plymouth/PinguyBuilder-theme/progress_bar.png',
                        theme_dir + '/progress_bar.png')
            shutil.copy('/etc/PinguyBuilder/plymouth/PinguyBuilder-theme/progress_box.png',
                        theme_dir + '/progress_box.png')
            script_name = "/lib/plymouth/themes/" + theme_name_fixed + "/" + theme_name_fixed + ".script"
            script = open(
                "/etc/PinguyBuilder/plymouth/PinguyBuilder-theme/PinguyBuilder-theme.script").read().replace(
                "__THEMEPIC__", os.path.basename(theme_pic))
            open(script_name, 'w+').write(script)

            config_name = "/lib/plymouth/themes/" + theme_name_fixed + "/" + theme_name_fixed + ".plymouth"
            config = open("/etc/PinguyBuilder/plymouth/PinguyBuilder-theme/PinguyBuilder-theme.plymouth").read()
            config = config.replace("__THEMENAME__", theme_name)
            config = config.replace("__THEMEDIR__", theme_name_fixed)
            open(config_name, 'w+').write(config)

            os.system(
                'update-alternatives --install /lib/plymouth/themes/default.plymouth default.plymouth "%(config_name)s" 80' % (
                {'config_name': config_name}))
            os.system(
                'update-alternatives --set default.plymouth "%(config_name)s"' % ({'config_name': config_name}))

            self.builder.get_object("checkbutton_window_plymouth_auto").set_active(False)

            self.update_initramfs()

            msg_info(
                _("Your plymouth theme named %(theme_name)s with the picture %(theme_pic)s has been created.") % (
                {'theme_name': theme_name, 'theme_pic': theme_pic}), self.window_main)
        else:
            dialog.destroy()
            shutil.rmtree(theme_dir)
        self.list_themes()

    def on_button_window_plymouth_ok_clicked(self, widget):
        if self.builder.get_object("checkbutton_window_plymouth_auto").get_active():
            os.system("update-alternatives --auto default.plymouth")
            self.update_initramfs()
            msg_info(_("Done! Now plymouth will use the default, auto-selected theme."), self.window_main)
        else:
            model, treeiter = self.builder.get_object("treeview_themes").get_selection().get_selected()
            if treeiter is None:
                msg_error(_("Please, select a theme!"), self.window_main)
                return
            theme = model.get(treeiter, 1)[0]
            os.system('update-alternatives --set default.plymouth "%s"' % theme)
            self.update_initramfs()
        self.builder.get_object("window_plymouth").hide()
        self.builder.get_object("window_main").show()

    def on_button_window_plymouth_cancel_clicked(self, widget, data = None):
        self.builder.get_object("window_plymouth").hide()
        self.builder.get_object("window_main").show()
    # END PLAYMOUTH HANDLERS

    def quit(self, widget, data = None):
        self.update_conf()
        Gtk.main_quit()
        exit(0)
        
    def load_settings(self):
        config_f = open(self.conffile)
        config_txt = config_f.read()
        config_f.close()
        
        self.builder.get_object("entry_username").set_text(
            self.getvalue('LIVEUSER', config_txt, 'custom'))

        self.builder.get_object("entry_cd_label").set_text(
            self.getvalue('LIVECDLABEL', config_txt, 'Custom Live CD'))

        self.builder.get_object("entry_filename").set_text(
            self.getvalue('CUSTOMISO', config_txt, 'custom-$1.iso'))

        self.builder.get_object("entry_exclude").set_text(
            self.getvalue('EXCLUDES', config_txt, ''))
    
        self.builder.get_object("entry_url_usb_creator").set_text(
            self.getvalue('LIVECDURL', config_txt, 'http://pinguyos.com'))

        self.builder.get_object("entry_squashfs_options").set_text(
            self.getvalue('SQUASHFSOPTS', config_txt, '-no-recovery -always-use-fragments -b 1M -no-duplicates'))

        self.builder.get_object("checkbutton_show_backup_icon").set_active(
            self.getvalue('BACKUPSHOWINSTALL', config_txt, '1') == '1')
        
        workdir = self.getvalue('WORKDIR', config_txt, '/home/PinguyBuilder')
        if not os.path.exists(workdir):
            os.makedirs(workdir)
        self.builder.get_object("entry_working_directory").set_text(workdir)
        
        self.builder.get_object("checkbutton_show_backup_icon").set_active(
            self.getvalue('BACKUPSHOWINSTALL', config_txt, '1').upper() == '1')

        self.builder.get_object("textview_sources_list").get_buffer().set_text(
            self.getvalue('SOURCESLIST', config_txt, ''))

        self.builder.get_object("textview_success_command").get_buffer().set_text(
            unescape_bash_script(self.getvalue('SUCCESSCOMMAND', config_txt, '')))

        self.builder.get_object("textview_first_boot_commands").get_buffer().set_text(
            unescape_bash_script(self.getvalue('FIRSTBOOTCOMMANDS', config_txt, '')))

    def update_conf(self):
        if self.builder.get_object("checkbutton_show_backup_icon").get_active():
            BACKUPSHOWINSTALL = '1'
        else:
            BACKUPSHOWINSTALL = '0'

        _buffer = self.builder.get_object("textview_sources_list").get_buffer()
        SOURCESLIST = _buffer.get_text(_buffer.get_start_iter(), _buffer.get_end_iter(), True)

        _buffer = self.builder.get_object("textview_success_command").get_buffer()
        SUCCESSCOMMAND = escape_bash_script(_buffer.get_text(_buffer.get_start_iter(), _buffer.get_end_iter(), True))

        _buffer = self.builder.get_object("textview_first_boot_commands").get_buffer()
        FIRSTBOOTCOMMANDS = escape_bash_script(_buffer.get_text(_buffer.get_start_iter(), _buffer.get_end_iter(), True))
            
        conf_content = '''
#PinguyBuilder Global Configuration File


# This is the temporary working directory and won't be included on the cd/dvd
WORKDIR="%(WORKDIR)s"


# Here you can add any other files or directories to be excluded from the live filesystem
# Separate each entry with a space
EXCLUDES="%(EXCLUDES)s"


# Here you can change the livecd/dvd username
LIVEUSER="%(LIVEUSER)s"


# Here you can change the name of the livecd/dvd label
LIVECDLABEL="%(LIVECDLABEL)s"


# Here you can change the name of the ISO file that is created
CUSTOMISO="%(CUSTOMISO)s"

# Here you can change the mksquashfs options
SQUASHFSOPTS="%(SQUASHFSOPTS)s"


# Here you can prevent the Install icon from showing up on the desktop in backup mode. 0 - to not show 1 - to show 
BACKUPSHOWINSTALL="%(BACKUPSHOWINSTALL)s"


# Here you can change the url for the usb-creator info
LIVECDURL="%(LIVECDURL)s"


# Here you can change the sources list for the current linux distro (default ubuntu 18.04.2 LTS)
SOURCESLIST="%(SOURCESLIST)s"


# Here you can add custom command to run in ubiquity success command
SUCCESSCOMMAND="%(SUCCESSCOMMAND)s"

# Here you can add custom commands to run in PinguyBuilder-firstboot service
FIRSTBOOTCOMMANDS="%(FIRSTBOOTCOMMANDS)s"
''' % ({
        "WORKDIR" : self.builder.get_object("entry_working_directory").get_text(),
        "EXCLUDES" : self.builder.get_object("entry_exclude").get_text(),
        "LIVEUSER" : self.builder.get_object("entry_username").get_text(),
        "LIVECDLABEL" : self.builder.get_object("entry_cd_label").get_text(),
        "CUSTOMISO" : self.builder.get_object("entry_filename").get_text(),
        "SQUASHFSOPTS" : self.builder.get_object("entry_squashfs_options").get_text(),
        "BACKUPSHOWINSTALL" : BACKUPSHOWINSTALL,
        "LIVECDURL" : self.builder.get_object("entry_url_usb_creator").get_text(),
        "SOURCESLIST": SOURCESLIST,
        "SUCCESSCOMMAND": SUCCESSCOMMAND,
        "FIRSTBOOTCOMMANDS": FIRSTBOOTCOMMANDS,
        })

        conf = open(self.conffile, 'w+')
        conf.write(conf_content)
        conf.close()
        
    def getvalue(self, name, conf, default):
        try:
            m = re.search(name+'="([^\\\\\\"]*(?:\\\\.[^\\\\\\"]*)*)"', conf)
            return m.group(1)
        except:
            return default


def msg_error(msg, window=None):
    dialog = Gtk.MessageDialog(
        window,
        Gtk.DialogFlags.MODAL,
        Gtk.MessageType.ERROR,
        Gtk.ButtonsType.OK, msg
    )
    dialog.set_transient_for(window)
    dialog.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
    dialog.run()
    dialog.destroy()


def msg_info(msg, window):
    dialog = Gtk.MessageDialog(
        window,
        Gtk.DialogFlags.MODAL,
        Gtk.MessageType.INFO,
        Gtk.ButtonsType.OK,
        msg
    )
    dialog.set_transient_for(window)
    dialog.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
    dialog.run()
    dialog.destroy()        


def msg_confirm(msg, window=None):
    dialog = Gtk.MessageDialog(
        window
        , Gtk.DialogFlags.DESTROY_WITH_PARENT
        , Gtk.MessageType.QUESTION
        , Gtk.ButtonsType.OK_CANCEL
        , msg
    )
    dialog.set_transient_for(window)
    dialog.set_position(Gtk.WindowPosition.CENTER_ON_PARENT)
    response = dialog.run()
    dialog.destroy()

    if response == Gtk.ResponseType.OK:
        return True
    else:
        return False


def msg_input(title, message, label, default='', window=None, password=False):
    def responseToDialog( entry, dialog, response):
        dialog.response(response)

    dialog = Gtk.MessageDialog(
        window,
        Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT,
        Gtk.MessageType.QUESTION,
        Gtk.ButtonsType.OK_CANCEL,
        None
    )
    dialog.set_transient_for(window)
    dialog.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
    dialog.set_markup(message)
    dialog.set_title(title)

    entry = Gtk.Entry()
    entry.set_text(default)
    entry.set_visibility(not password)
    entry.connect("activate", responseToDialog, dialog, Gtk.ResponseType.OK)
    hbox = Gtk.HBox()
    hbox.pack_start(Gtk.Label(label, True, True, 0), False, 5, 5)
    hbox.pack_end(entry, True, True, 0)
    dialog.vbox.pack_end(hbox, True, True, 0)
    dialog.show_all()
    response = dialog.run()
    text = entry.get_text()
    dialog.destroy()
    
    if response == Gtk.ResponseType.OK:
        return text
    else:
        return None


def escape_bash_script(script):
    return script.replace('\\', '\\\\').replace('\"', '\\\"')


def unescape_bash_script(script):
    return script.replace('\\\"', '\"').replace('\\\\', '\\')


class Namespace: pass


if os.popen('whoami').read().strip() != 'root':
    os.chdir(os.path.dirname(os.path.realpath(__file__)))
    if os.system('which gksu') == 0:
        if os.path.exists('/usr/share/applications/PinguyBuilder-Gtk.desktop'):
            os.system('gksu -D "%s" python ./PinguyBuilder_Gtk.py' % _('PinguyBuilder'))
        else:
            os.system('gksu -D "%s" python ./PinguyBuilder_Gtk.py' % '/usr/share/applications/PinguyBuilder-Gtk.desktop')
    elif os.system('which kdesudo') == 0:
        os.system('kdesudo ./PinguyBuilder_Gtk.py')
    elif os.system('which sudo') == 0:
        password = msg_input(_(''),
                             _('Enter your password to perform administrative tasks'), 'Password:', '', None, True)
        if password:
            os.popen('sudo -S python ./PinguyBuilder_Gtk.py', 'w').write(password)
else:
    if __name__ == '__main__':
        app = Appgui()
        Gtk.main()

