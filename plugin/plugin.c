/* 
 * Copyright (c) 2006 rPath, Inc.
 *
 * This program is distributed under the terms of the Common Public License,
 * version 1.0. A copy of this license should have been distributed with this
 * source file in a file called LICENSE. If it is not present, the license
 * is always available at http://www.opensource.org/licenses/cpl.php.
 *
 * This program is distributed in the hope that it will be useful, but
 * without any warranty; without even the implied warranty of merchantability
 * or fitness for a particular purpose. See the Common Public License for
 * full details.
 *
 * vim: set sw=4: -*- Mode: C; tab-width: 4; indent-tabs-mode: t; c-basic-offset: 4 -*-
*/

#define XP_UNIX 1
#define MOZ_X11 1
#include "npapi.h"
#include "npupp.h"

NPError NP_GetValue(void *future, NPPVariable var, void *val) {
	NPError err = NPERR_NO_ERROR;

	switch (var) {
	case NPPVpluginNameString:
		*((char **) val) = "rMake stub plugin";
		break;
	case NPPVpluginDescriptionString:
		*((char **) val) = ("rMake stub plugin - used to detect "
				    "the installation of rMake.");
		break;
	default:
		err = NPERR_GENERIC_ERROR;
	}
	return err;
}

char * NP_GetMIMEDescription (void) {
    return ("application/x-rmake::rMake build service;"
	    "application/x-rmake;version=1.0::rMake build service;"
	    "application/x-rmake;subscriberApiVer=1::rMake build service;");
}

NPError NP_Initialize(NPNetscapeFuncs *moz_funcs,
					  NPPluginFuncs *plugin_funcs) {
	if (moz_funcs == NULL || plugin_funcs == NULL)
		return NPERR_INVALID_FUNCTABLE_ERROR;

	if ((moz_funcs->version >> 8) > NP_VERSION_MAJOR)
		return NPERR_INCOMPATIBLE_VERSION_ERROR;
	if (moz_funcs->size < sizeof (NPNetscapeFuncs))
		return NPERR_INVALID_FUNCTABLE_ERROR;
	if (plugin_funcs->size < sizeof (NPPluginFuncs))
		return NPERR_INVALID_FUNCTABLE_ERROR;

	plugin_funcs->version = (NP_VERSION_MAJOR << 8) + NP_VERSION_MINOR;
	plugin_funcs->size = sizeof (NPPluginFuncs);

	return NPERR_NO_ERROR;
}

NPError NP_Shutdown (void) {
	return NPERR_NO_ERROR;
}
