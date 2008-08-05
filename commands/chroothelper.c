/*
 * Copyright (c) 2006 rPath, Inc.
 *
 * This program is distributed under the terms of the Common Public License,
 * version 1.0. A copy of this license should have been distributed with this
 * source file in a file called LICENSE. If it is not present, the license
 * is always available at http://www.rpath.com/permanent/licenses/CPL-1.0.
 *
 * This program is distributed in the hope that it will be useful, but
 * without any warranty; without even the implied warranty of merchantability
 * or fitness for a particular purpose. See the Common Public License for
 * full details.
 *
 *
 * Rmake chroot helper - setuid program to enter chroots for rmake.
 *
 * usage:     chroothelper <path/to/chroot>
 *              - creates necessary mount points, dev nodes,
 *                and switches to CHROOT_USER
 *
 *         OR chroothelper <path/to/chroot> --clean
 *              - removes mount points, cleans up files owned by
 *                CHROOT_USER.
 *
 * The program must be run as RMAKE_USER, the directory about the chroot
 * must be owned by RMAKE_USER.
 *
 * This program should be kept as small as possible to try to avoid security
 * holes.
 */

#define _GNU_SOURCE
#include <features.h>

#include <errno.h>
#include <dirent.h>
#include <fcntl.h>
#include <getopt.h>
#include <grp.h>
#include <pwd.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include <sys/capability.h>
#include <sys/mount.h>
#include <sys/param.h>
#include <sys/prctl.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>

/* needed for personality setting */
#include <syscall.h>
#include <linux/personality.h>
#include <sys/utsname.h>
#define set_pers(pers) ((long)syscall(SYS_personality, pers))

#include "chroothelper.h"

/* global option for verbose execution */
int opt_verbose = 0;

struct passwd * get_user_entry(const char * userName) {
    struct passwd * pwent;
    int errno;

    errno = 0;
    pwent = getpwnam(userName);
    if (errno != 0) {
        perror("getpwnam");
        return NULL;
    }

    if (pwent == NULL) {
        fprintf(stderr, "error: Could not find user '%s' in /etc/passwd\n", userName);
        return NULL;
    }

    return pwent;
}

int switch_to_uid_gid(int uid, int gid) {
    if (-1 == setgroups(0, NULL)) {
        perror("setgroups");
        return 1;
    }
    if (-1 == setgid(gid)) {
        perror("setgid");
        return 1;
    }
    if (-1 == setuid(uid)) {
        perror("setuid");
        return 1;
    }
    return 0;
}

int switch_to_user(const char * userName) {
    struct passwd * pwent;
    pwent = get_user_entry(userName);

    if (opt_verbose)
	printf("switching uid/gid to %s\n", userName);

    if (pwent == NULL){
	fprintf(stderr, "ERROR: could not find pwent for %s\n", userName);
        return 1;
    }
    return switch_to_uid_gid(pwent->pw_uid, pwent->pw_gid);
}

int mount_dir(const char * chrootDir, const char * fromDir,
              const char * toDir,     const char * mountType) {
    int rc;
    struct stat st;
    char tempPath[PATH_MAX];

    rc = snprintf(tempPath, PATH_MAX, "%s%s", chrootDir, toDir);
    if (rc > PATH_MAX) {
        fprintf(stderr, "mount: path too long\n");
        return 1;
    } else if(rc < 0) {
        perror("snprintf");
        return 1;
    }
    if (opt_verbose)
        printf("mount %s -> %s (type %s)\n", fromDir, tempPath, mountType);
    /* check destination directory exists */
    rc = stat(tempPath, &st);
    if (rc == -1 || !S_ISDIR(st.st_mode)) {
        fprintf(stderr, "ERROR: %s should be an existing directory\n", tempPath);
        return 1;
    }
    if (-1 == mount(fromDir, tempPath, mountType, 0, NULL)) {
        perror("mount");
        /* don't error out on mount errors - if it's already mounted - great!*/
    }
    return 0;
}

int do_chroot(const char * chrootDir) {
    /* Enter in chroot and cd / */
    if (opt_verbose)
	printf("chroot %s\n", chrootDir);
    if (-1 == chroot(chrootDir)) {
        perror("chroot");
        return 1;
    }

    if (-1 == chdir("/")) {
        perror("chroot");
        return 1;
    }
    return 0;
}

/***********************************************************
 *
 * --clean/--unmount command
 *
 * enters chroot, unmounts partitions, and removes CHROOT_USER files
 * from /tmp and /var/tmp (the only place they should be able to write
 *
 *********************************************************/
int unmountchroot(const char * chrootDir, int opt_clean) {
    char childPath[PATH_MAX];
    int i;
    int rc;
    uid_t myUid;
    pid_t pid;
    struct stat statInfo;
    DIR * dir_h;
    struct dirent * dirent_h;
    struct passwd * chrootent;

    char * tmpDirs[] = { "/tmp", "/var/tmp" };
    if (opt_verbose)
	printf("unmounting/cleaning %s\n", chrootDir);

    /* get chroot user uid/gid from outside the chroot */
    chrootent = get_user_entry(CHROOT_USER);
    if (chrootent == NULL) {
      return 1;
    }

    /*enter chroot */
    rc = do_chroot(chrootDir);
    if (rc != 0) {
        return rc;
    }

    /* we still need to be root to umount */
    for (i=0; i < (sizeof(mounts) / sizeof(mounts[0])); i++) {
	if (opt_verbose)
	    printf("umount %s\n", mounts[i].to);
        if (-1 == umount(mounts[i].to)) {
            perror("umount");
        }
    }
    if (opt_verbose)
        printf("umount %s\n", "/tmp");
    if (-1 == umount("/tmp")) {
        perror("umount /tmp");
    }

    /* We only want to remove files owned by chrootuid, everything
     * else we should be able to delete elsewhere */
    rc = switch_to_uid_gid(chrootent->pw_uid, chrootent->pw_gid);
    if (rc)
	return rc;
    if (!opt_clean)
        return 0;

    myUid = getuid();
    if (opt_verbose)
	printf("deleting temporary directories... uid=%d\n", myUid);

    for(i = 0; i < sizeof(tmpDirs) / sizeof(tmpDirs[0]); i++) {
        errno = 0;
        if (NULL == (dir_h = opendir(tmpDirs[i]))) {
            continue;
        }
	if (opt_verbose)
	    printf("deleting files in %s\n", tmpDirs[i]);

        while ((dirent_h = readdir(dir_h))) {
            if ((strcmp(dirent_h->d_name, ".") == 0) ||
                (strcmp(dirent_h->d_name, "..") == 0)) {
                continue;
            }
            rc = snprintf(childPath, PATH_MAX, "%s/%s",
                          tmpDirs[i], dirent_h->d_name);
            if (opt_verbose)
                printf("  deleting %s\n", childPath);
            if ((rc > PATH_MAX) || (rc < 0)) {
                /* silently ignore paths that are too long - this is
                   not a major deal */
                continue;
            }
            if (-1 == stat(childPath, &statInfo) ) {
                /* we can't access this file, we can't erase it */
                continue;
            }
            if (statInfo.st_uid != myUid) {
                if (opt_verbose)
                    fprintf(stderr, "owned by %d, not %d\n", statInfo.st_uid, myUid);
                /* we don't own this file, we can't remove it. */
                continue;
            }
            pid = fork();
            if (pid == 0) {
                execl("/sbin/busybox", "/sbin/busybox", "rm", "-rf", 
                      childPath, NULL);
                /* this will not return unless error */
                perror("execl");
                _exit(1);
            } else {
                int status;
                if (-1 == waitpid(pid, &status, 0)) {
                    perror("waitpid");
                    return 1;
                }
                else if (!WIFEXITED(status)) {
                    fprintf(stderr, "warning: rm -rf exited abnormally\n");
                    return 1;
                }
                else if (WEXITSTATUS(status) != 0) {
                    /* don't raise an error - this is expected */
                    ;
                }
            }
        }
    }

    if (opt_verbose)
        printf("deleting other files owned by  uid=%d\n", myUid);
    pid = fork();
    if (pid == 0) {
        execl("/sbin/busybox", "/sbin/busybox",  "sh", "-c", "/sbin/busybox find / | /sbin/busybox sh -c 'while read file; do if `/sbin/busybox test -O $file`; then /sbin/busybox rm -rf $file; fi; done'", NULL);
        /* this will not return unless error */
        perror("execl");
        _exit(1);
    } else {
        int status;
        if (-1 == waitpid(pid, &status, 0)) {
            perror("waitpid");
            return 1;
        }
        else if (!WIFEXITED(status)) {
            fprintf(stderr, "error: cleanup exited abnormally\n");
            return 1;
        }
        else if (WEXITSTATUS(status) != 0) {
            fprintf(stderr, "error: cleanup exited abnormally\n");
            return 1;
            ;
        }
    }

    return 0;
}


/***********************************************************
 *
 * chroot helper main functionality
 *
 * mounts partitions, drops extra privileges,
 * makes nodes and creates dev symlinks as RMAKE_USER, then
 * enters chroot, runs tag scripts, switches to CHROOT_USER,
 * and execs the chroot server.
 *
 *********************************************************/

int enter_chroot(const char * chrootDir, const char * socketPath,
                 int useTmpfs, int useChrootUser, int runTagScripts) {
    cap_t cap;
    int i;
    int rc;
    pid_t pid;
    char tempPath[PATH_MAX];
    char command[PATH_MAX]; /* this may fail as our command could be longer
                             * than this, but it really shouldn't be 
                             * unless someone's abusing the system */

    /* do the mounting here, since there is no mount capability */
    for(i=0; i < (sizeof(mounts) / sizeof(mounts[0])); i++) {
        if ((rc = mount_dir(chrootDir, mounts[i].from,
                           mounts[i].to, mounts[i].type)))
            return rc;
    }
    if (useTmpfs) {
        if ((rc = mount_dir(chrootDir, "/tmp", "/tmp", "tmpfs")))
            return rc;
    }

    /* we need to allow creation of 666 devices */
    umask(0);
    /* make sure we create all nodes as root.root */
    if ((rc = switch_to_uid_gid(0, 0)))
        return rc;
    /* mknod here */
    for(i=0; i < (sizeof(devices) / sizeof(devices[0])); i++) {
        struct devinfo_t device = devices[i];

        rc = snprintf(tempPath, PATH_MAX, "%s/dev/%s", chrootDir, device.path);
        if (rc > PATH_MAX) {
            fprintf(stderr, "error: mknod: path too long\n");
            return 1;
        } else if(rc < 0) {
            perror("snprintf");
            return 1;
        }
	if (opt_verbose)
	    printf("creating device %s\n", tempPath);

        if (-1 == mknod(tempPath, device.type | device.mode,
                        makedev(device.major, device.minor))) {
            if (errno != EEXIST) {
                perror("mknod");
                return 1;
            }
        }
    }
    /* restore sane umask */
    umask(0002);



    /* keep our capabilities as we transition back to our real uid */
    prctl(PR_SET_KEEPCAPS, 1, 0, 0, 0);

    if (switch_to_user(RMAKE_USER)) {
	fprintf(stderr, "ERROR: can not assume %s privileges\n", RMAKE_USER);
	return -1;
    }

    /* also initgroups here */

    /* retain chroot() and mknod() */
    cap = cap_from_text("cap_sys_chroot,cap_setuid,cap_setgid+ep");
    if (NULL == cap) {
        perror("cap_from_text");
        return 1;
    }
    if (0 != cap_set_proc(cap)) {
        perror("cap_set_proc");
        return 1;
    }
    cap_free(cap);

    /* make required symlinks */
    for(i=0; i < (sizeof(symlinks) / sizeof(symlinks[0])); i++) {
        rc = snprintf(tempPath, PATH_MAX, "%s%s", chrootDir, symlinks[i].from);
        if (rc > PATH_MAX) {
            fprintf(stderr, "error: symlink: path too long\n");
            return 1;
        } else if(rc < 0) {
            perror("snprintf");
            return 1;
        }
	if (opt_verbose)
	    printf("creating symlink: %s -> %s\n", tempPath, symlinks[i].to);
        unlink(tempPath);
        if(-1 == symlink(symlinks[i].to, tempPath)) {
            perror("symlink");
            return 1;
        }
    }

    /* chroot, then run tag scripts, then switch to chroot uid */
    do_chroot(chrootDir);
    if (runTagScripts) {
        pid = fork();
        if (pid == 0) {
            /* run with the environment set up inside the shell */
            execle("/bin/sh", "/bin/sh", "-l", "/root/tagscripts", NULL, env);
            perror("execl");
            _exit(1);
        }
        else {
            int status;
            if (-1 == waitpid(pid, &status, 0)) {
                perror("waitpid");
                return 1;
            }
            else if (!WIFEXITED(status)) {
                if (WIFSIGNALED(status)) {
                    fprintf(stderr, "error: tag scripts exited abnormally with signal %d\n", WTERMSIG(status));
                }
                else {
                    fprintf(stderr, "error: tag scripts exited abnormally\n");
                }
                return 1;
            }
            else if (WEXITSTATUS(status) != 0) {
                fprintf(stderr, "error: tag scripts exited with status %d\n", WEXITSTATUS(status));
                return 1;
            }
        }
    }

    if (useChrootUser && switch_to_user(CHROOT_USER)) {
        fprintf(stderr, "ERROR: can not assume %s privileges\n", CHROOT_USER);
        return -1;
    }
    rc = snprintf(command, PATH_MAX,
                  "%s %s start -n --socket %s", "/usr/bin/python",
                  CHROOT_SERVER_PATH, socketPath);
    if (rc >= PATH_MAX) {
        fprintf(stderr, "ERROR: command too long\n");
        return 1;
    }
    if (opt_verbose)
	printf("executing: %s\n", command);
    execle("/bin/sh", "/bin/sh", "-lc", command, NULL, env);
    perror("execl");
    return 1;
}

int assert_correct_perms(const char * chrootDir) {
    char parentDir[PATH_MAX];
    struct passwd * pwent;
    uid_t rmake_uid;
    gid_t rmake_gid;
    struct stat statInfo;
    int copied;

    errno = 0;
    pwent = getpwnam(RMAKE_USER);
    if (errno != 0) {
        perror("getpwnam");
        return 1;
    }

    if (pwent == NULL) {
        fprintf(stderr, "error: Could not find user '%s' in /etc/passwd\n", RMAKE_USER);
        return 1;
    }
    rmake_uid = pwent->pw_uid;
    rmake_gid = pwent->pw_gid;

    /* if we're not setuid root, display a message */
    if (0 != geteuid()) {
        fprintf(stderr, "error: suidhelper must be suid root\n");
        return 1;
    }

    /* if we're already root, there isn't anything to do */
    if (getuid() == 0) {
        printf("You are already root\n");
    }
    else if ((rmake_uid != getuid()) || (rmake_gid != getgid())) {
        fprintf(stderr, "error: chroothelper can only be run by the rmake user\n");
        return 1;
    }

    /* This directory may not exist in all cases...
       the parent's perms are very stringent...
    */

    if(-1 == stat(chrootDir, &statInfo) ) {
        perror("stat");
        return 0;
    }

    if ((rmake_uid != statInfo.st_uid) || (rmake_gid != statInfo.st_gid)) {
        fprintf(stderr, "error: chroot must be owned by the rmake user and group\n");
        return 1;
    }

    /* we need to check permissions of the chroot's real parent directory
     * since we've created tmp dirs in the subdirectory with 1777 permissions
     */

    /* get the real parent directory of chrootDir */
    strncpy(parentDir, chrootDir, PATH_MAX);
    copied = strlen(chrootDir);
    if(copied + 4 > PATH_MAX) {
        fprintf(stderr, "error: chroot path too long\n");
    }
    strncpy(&(parentDir[copied]), "/..", 4);

    if(-1 == stat(parentDir, &statInfo)) {
        perror("stat");
        return 1;
    }

    if ((rmake_uid != statInfo.st_uid) || (rmake_gid != statInfo.st_gid)) {
        fprintf(stderr, "error: chroot parent directory must be owned by the rmake user and group\n");
        return 1;
    }
    if ((statInfo.st_mode & 07777) != (S_IWUSR | S_IRUSR | S_IXUSR)) {
        fprintf(stderr, "error: chroot parent directory must be mod 0700\n");
        return 1;
    }

    return 0;
}

void usage(char *progname)
{
    fprintf(stderr, "usage: %s [--arch <arch>] [--clean] [--unmount] <path>\n", progname);
};

int main(int argc, char **argv)
{
    int rc;

    int opt_clean = 0; /* set if we need to clean */
    int opt_unmount = 0; /* set if we need to unmount only */
    int opt_tmpfs = 0; /* set if we are using tmpfs */
    int opt_noChrootUser = 0; /* set if we should not use the chroot user 
                                 but instead stay as the rmake user.
                                 (useful for debugging)
                               */
    int opt_noTagScripts = 0; /* set if we should not run tag scripts */
    char * archname = NULL;
    char * chrootDir = NULL;
    char * socketPath = NULL;

    struct option main_options[] = {
	{"tmpfs", no_argument, &opt_tmpfs, 1},
	{"no-chroot-user", no_argument, &opt_noChrootUser, 1},
	{"no-tag-scripts", no_argument, &opt_noTagScripts, 1},
	{"clean", no_argument, &opt_clean, 1},
	{"unmount", no_argument, &opt_unmount, 1},
	{"arch", required_argument, NULL, 'a'},
	{"help", no_argument, NULL, 'h'},
	{"verbose", no_argument, &opt_verbose, 1},
	{0, 0, 0, 0}
    };

    while (1) {
	rc = getopt_long(argc, argv, "a:chv", main_options, NULL);
	if (rc == -1)
	    break;

	/* parse options */
	switch(rc) {
	    case 'a': /* set the a new architecture personality */
		archname = strndup(optarg, 10);
		break;
	    case 'h': /* help/usage */
		usage(argv[0]);
		return 0;
	    case 'v':
		opt_verbose++;
		break;
	    case 0: /* other valid flag */
		break;
	    default:
		fprintf (stderr, "?? getopt returned character code 0%o ??\n", rc);
		usage(argv[0]);
		return -1;
	}
    }

    /* grab the requested chroot dir */
    if (optind < argc) {
	if (strlen(argv[optind]) >= PATH_MAX) {
	    usage(argv[0]);
	    return -2;
	}
	chrootDir = strndup(argv[optind++], PATH_MAX);
    } else {
	usage(argv[0]);
	return -1;
    }
    /* grab the requested socket path */
    if (!(opt_clean || opt_unmount)) {
        if (optind < argc) {
            if (strlen(argv[optind]) >= PATH_MAX) {
                usage(argv[0]);
                return -2;
            }
            socketPath = strndup(argv[optind++], PATH_MAX);
        } else {
            usage(argv[0]);
            return -1;
        }
    }
    /* we can only have one path as an arg */
    if (optind != argc) {
	usage(argv[0]);
	return -1;
    }

    /* Do permissions checks - make sure everything is sane */
    rc = assert_correct_perms(chrootDir);
    if (rc != 0) {
        fprintf(stderr, "permissions check failed\n");
        return rc;
    }
    if (opt_clean || opt_unmount)
	return unmountchroot(chrootDir, opt_clean);

    /* check if we need to do a 32bit setarch */
    if (archname) {
	if (
#if defined(__x86_64__) || defined(__i386__)
	    (strcmp(archname, "x86") == 0) ||
#endif
#if defined(__powerpc__) || defined(__powerpc64__)
	    (strcmp(archname, "ppc") == 0) ||
#endif
#if defined(__sparc64__) || defined(__sparc__)
	    (strcmp(archname, "sparc") == 0) ||
#endif
	    (strcmp(archname, "linux32") == 0)
	    ) {
	    struct utsname un;
	    if (opt_verbose)
		printf("%s: setting arch to %s\n", argv[0], archname);
	    rc = set_pers(PER_LINUX32);
	    if (rc == -EINVAL) {
		fprintf(stderr, "ERROR setting personality to %s\n", archname);
		return 1;
	    }
	    uname(&un);
	    if (opt_verbose)
		printf("%s: changed machine personality to %s\n", argv[0], un.machine);
	}
    }
    /* finally, start the work */
    return enter_chroot(chrootDir, socketPath, opt_tmpfs, !opt_noChrootUser,
                        !opt_noTagScripts);
}
