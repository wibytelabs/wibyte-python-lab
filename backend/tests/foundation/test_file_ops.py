"""Actual stdlib helper against private filesystem fixtures, no Docker/student data."""
import errno
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from backend.app.runtime import file_ops as ops


class FileOperationTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.base=Path(self.directory.name);self.root=self.base/'workspace';self.root.mkdir()
        self.outside=self.base/'outside';self.outside.mkdir();(self.outside/'private').write_bytes(b'outside marker')
        self.workspace=ops.Workspace(str(self.root));self.addCleanup(self.workspace.__exit__)

    def test_normal_utf8_nested_create_list_read_write_directory_rename_and_recursive_delete(self):
        self.workspace.mkdir('course/week')
        self.workspace.write('course/week/hello.py','print("π")\n'.encode(),exclusive=True)
        self.assertEqual(self.workspace.read('course/week/hello.py').decode(),'print("π")\n')
        self.assertEqual(self.workspace.list('course/week'),[{'name':'hello.py','type':'file'}])
        self.workspace.write('course/week/hello.py',b'new content')
        self.workspace.rename('course/week','archive/week')
        self.assertEqual(self.workspace.read('archive/week/hello.py'),b'new content')
        self.workspace.delete('archive');self.assertFalse((self.root/'archive').exists())
        self.assertEqual((self.outside/'private').read_bytes(),b'outside marker')

    def test_path_traversal_absolute_empty_control_backslash_and_root_mutations_are_denied(self):
        for value in ('','/etc/passwd','../outside/private','a/../../private','a//b','a/./b','a/../b','a\\b','bad\nname','bad\x7fname'):
            with self.subTest(path=value):
                with self.assertRaises(ops.FileOperationError):self.workspace.write(value,b'blocked')
        for action in (lambda:self.workspace.write('.',b'blocked'),lambda:self.workspace.mkdir('.'),lambda:self.workspace.delete('.'),
            lambda:self.workspace.rename('.','other'),lambda:self.workspace.rename('other','.')):
            with self.assertRaises(ops.FileOperationError):action()
        self.assertEqual(self.workspace.list('.'),[])

    def test_git_components_are_protected_gitignore_is_regular_and_root_listing_hides_git(self):
        (self.root/'.git').mkdir();(self.root/'.git'/'config').write_bytes(b'protected')
        self.workspace.write('.gitignore',b'*.pyc\n')
        self.assertEqual(self.workspace.list(),[{'name':'.gitignore','type':'file'}])
        for value in ('.git','.git/config','course/.git/config'):
            with self.assertRaises(ops.FileOperationError):self.workspace.write(value,b'blocked')
        (self.root/'project').mkdir();(self.root/'project'/'.git').mkdir()
        with self.assertRaises(ops.FileOperationError):self.workspace.delete('project')
        with self.assertRaises(ops.FileOperationError):self.workspace.rename('project','moved')
        self.assertTrue((self.root/'project'/'.git').is_dir())

    def test_symlink_parents_targets_and_symlinked_trusted_root_do_not_expose_outside(self):
        (self.root/'link').symlink_to(self.outside,target_is_directory=True)
        (self.root/'file').symlink_to(self.outside/'private')
        for action in (lambda:self.workspace.read('file'),lambda:self.workspace.write('file',b'blocked'),lambda:self.workspace.read('link/private'),
            lambda:self.workspace.write('link/private',b'blocked'),lambda:self.workspace.delete('link'),lambda:self.workspace.rename('file','renamed')):
            with self.assertRaises((ops.FileOperationError,OSError)):action()
        alias=self.base/'alias';alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(OSError):ops.Workspace(str(alias))
        self.assertEqual((self.outside/'private').read_bytes(),b'outside marker')

    def test_nonregular_fifo_hardlink_and_oversize_file_are_denied_across_operations(self):
        os.mkfifo(self.root/'fifo')
        (self.root/'hard').hardlink_to(self.outside/'private')
        with open(self.root/'large','wb') as stream:stream.truncate(ops.LIMIT+1)
        for name in ('fifo','hard','large'):
            for action in (lambda name=name:self.workspace.read(name),lambda name=name:self.workspace.write(name,b'blocked'),
                lambda name=name:self.workspace.rename(name,name+'-new'),lambda name=name:self.workspace.delete(name)):
                with self.subTest(file=name):
                    with self.assertRaises(ops.FileOperationError):action()
        self.assertEqual((self.outside/'private').read_bytes(),b'outside marker')
        self.assertEqual(self.root.joinpath('large').stat().st_size,ops.LIMIT+1)

    def test_real_ten_mib_boundary_and_oversized_new_write_fail_before_creating_parents(self):
        data=b'x'*ops.LIMIT;self.workspace.write('limit',data)
        self.assertEqual(len(self.workspace.read('limit')),ops.LIMIT)
        with self.assertRaises(ops.FileOperationError) as rejected:self.workspace.write('new/too-large',data+b'x')
        self.assertEqual(rejected.exception.code,13);self.assertFalse((self.root/'new').exists())
        self.assertEqual((self.root/'limit').stat().st_size,ops.LIMIT)

    def test_atomic_replace_failure_retains_old_bytes_and_cleans_only_its_owned_temporary(self):
        target=self.root/'editor.py';target.write_bytes(b'old bytes');target.chmod(0o750)
        foreign=self.root/'.wpl-edit-foreign';foreign.write_bytes(b'foreign')
        with patch.object(ops.os,'replace',side_effect=OSError(errno.EIO,'synthetic replacement failure')):
            with self.assertRaises(OSError):self.workspace.write('editor.py',b'new bytes')
        self.assertEqual(target.read_bytes(),b'old bytes');self.assertEqual(foreign.read_bytes(),b'foreign')
        self.assertEqual(sorted(path.name for path in self.root.glob('.wpl-edit-*')),['.wpl-edit-foreign'])
        self.workspace.write('editor.py',b'new bytes');self.assertEqual(target.read_bytes(),b'new bytes')
        self.assertEqual(target.stat().st_mode&0o777,0o750)
        print('Actual atomic editor replacement: injected failure kept old bytes and foreign temp; owned temporary removed; successful replacement preserved mode.',flush=True)

    def test_temporary_name_substitution_is_not_removed_by_failure_cleanup(self):
        (self.root/'editor').write_bytes(b'old')
        substituted=[]
        def substitute(source,_destination,**kwargs):
            parent=kwargs['src_dir_fd'];os.unlink(source,dir_fd=parent)
            os.symlink(str(self.outside/'private'),source,dir_fd=parent);substituted.append(source)
            raise OSError(errno.EIO,'synthetic substitution')
        with patch.object(ops.os,'replace',side_effect=substitute):
            with self.assertRaises(OSError):self.workspace.write('editor',b'new')
        self.assertTrue((self.root/substituted[0]).is_symlink())
        self.assertEqual((self.root/'editor').read_bytes(),b'old')
        self.assertEqual((self.outside/'private').read_bytes(),b'outside marker')

    def test_parent_symlink_swap_reads_only_the_already_open_workspace_directory(self):
        (self.root/'directory').mkdir();(self.root/'directory'/'private').write_bytes(b'inside')
        original=ops.os.open;swapped=[]
        def opening(path,flags,*args,**kwargs):
            descriptor=original(path,flags,*args,**kwargs)
            if path=='directory' and flags&os.O_DIRECTORY and not swapped:
                swapped.append(True);(self.root/'directory').rename(self.root/'retained')
                (self.root/'directory').symlink_to(self.outside,target_is_directory=True)
            return descriptor
        with patch.object(ops.os,'open',side_effect=opening):self.assertEqual(self.workspace.read('directory/private'),b'inside')
        with self.assertRaises(OSError):self.workspace.read('directory/private')
        self.assertEqual((self.outside/'private').read_bytes(),b'outside marker')

    def test_editor_target_swap_is_detected_before_replace_and_cannot_write_through_outside_link(self):
        target=self.root/'editor';target.write_bytes(b'old');original=ops.os.fsync;swapped=[]
        def syncing(descriptor):
            if not swapped:
                swapped.append(True);target.unlink();target.symlink_to(self.outside/'private')
            return original(descriptor)
        with patch.object(ops.os,'fsync',side_effect=syncing):
            with self.assertRaises(ops.FileOperationError) as rejected:self.workspace.write('editor',b'new')
        self.assertEqual(rejected.exception.code,14)
        self.assertEqual((self.outside/'private').read_bytes(),b'outside marker')
        self.assertEqual(list(self.root.glob('.wpl-edit-*')),[])

    def test_linux_no_overwrite_rename_handles_a_concurrent_destination_creation(self):
        (self.root/'source').write_bytes(b'source bytes');original=ops.no_replace
        def racing(source_parent,source,destination_parent,destination):
            descriptor=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600,dir_fd=destination_parent)
            os.write(descriptor,b'concurrent destination');os.close(descriptor)
            return original(source_parent,source,destination_parent,destination)
        with patch.object(ops,'no_replace',side_effect=racing):
            with self.assertRaises(FileExistsError):self.workspace.rename('source','destination')
        self.assertEqual((self.root/'source').read_bytes(),b'source bytes')
        self.assertEqual((self.root/'destination').read_bytes(),b'concurrent destination')

    def test_tree_and_listing_bounds_fail_before_rename_or_delete_mutates_the_tree(self):
        self.workspace.mkdir('tree/deeper/deepest')
        self.workspace.write('tree/a',b'1234');self.workspace.write('tree/b',b'5678')
        for limit,value in (('MAX_TREE_BYTES',6),('MAX_ENTRIES',2),('MAX_DEPTH',2)):
            with patch.object(ops,limit,value):
                for action in (lambda:self.workspace.delete('tree'),lambda:self.workspace.rename('tree','moved')):
                    with self.assertRaises(ops.FileOperationError) as rejected:action()
                    self.assertEqual(rejected.exception.code,13)
            self.assertEqual(self.workspace.read('tree/a'),b'1234');self.assertTrue((self.root/'tree/deeper/deepest').exists())
        with patch.object(ops,'MAX_ENTRIES',1):
            with self.assertRaises(ops.FileOperationError):self.workspace.list('tree')
        self.assertFalse((self.root/'moved').exists())

    def test_argument_data_separation_preserves_shell_metacharacters_and_does_not_execute_them(self):
        name="spaces ; $(touch escaped) ' quoted.py"
        self.workspace.write(name,b'synthetic code')
        self.assertEqual(self.workspace.read(name),b'synthetic code');self.assertFalse((self.root/'escaped').exists())
        result=subprocess.run([sys.executable,'-I',ops.__file__,'read',str(self.root),name],capture_output=True,timeout=5)
        self.assertEqual(result.returncode,0);self.assertEqual(result.stdout,b'synthetic code')

    def test_actual_helper_protocol_is_bounded_and_failed_operations_do_not_leak_descriptors(self):
        before=len(list(Path('/proc/self/fd').iterdir()))
        for _index in range(30):
            with self.assertRaises(FileNotFoundError):self.workspace.read('missing/file')
        self.assertEqual(len(list(Path('/proc/self/fd').iterdir())),before)
        os.mkfifo(self.root/'fifo')
        for action,path,expected in (('read','fifo',10),('read','missing',12),('delete','.',10),('read','../outside/private',10)):
            result=subprocess.run([sys.executable,'-I',ops.__file__,action,str(self.root),path],capture_output=True,timeout=5)
            self.assertEqual(result.returncode,expected);self.assertEqual(result.stdout,b'');self.assertEqual(result.stderr,b'')
