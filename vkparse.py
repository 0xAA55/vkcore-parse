#!/usr/bin/env python3
# -*- coding: utf-8 -*
import io
import os
import json

# The `pushd()` implementation from `https://gist.github.com/howardhamilton/537e13179489d6896dd3`
from contextlib import contextmanager

@contextmanager
def pushd(new_dir):
	previous_dir = os.getcwd()
	if len(new_dir):
		os.chdir(new_dir)
	try:
		yield
	finally:
		os.chdir(previous_dir)

def to_snake(camel_case):
	ret = ''
	uppers = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ')
	last_is_upper = False
	for a in camel_case:
		if a in uppers:
			if last_is_upper == False:
				last_is_upper = True
				ret += f'_{a.lower()}'
			else:
				ret += a.lower()
		else:
			if last_is_upper == True:
				last_is_upper = False
			ret += a
	while ret[0] == '_': ret = ret[1:]
	while '__' in ret: ret = ret.replace('__', '_')
	return ret

def to_camel(snake_case, first_is_upper = False):
	ret = ''
	next_should_upper = first_is_upper
	for a in snake_case.lower():
		if a == '_':
			next_should_upper = True
		elif a.isalpha():
			if next_should_upper:
				ret += a.upper()
				next_should_upper = False
			else:
				ret += a
		else:
			ret += a
	return ret


def parse(input, initial = {}, is_include_header = 0):
	ret = initial
	cur_ver = ''
	sharp_if_level = 0
	is_enum = False
	is_union = False
	is_struct = False
	is_proto = False
	is_cpp = False
	is_typedef_func = False
	is_multiline_comment = False
	cur_func = {}
	cur_enum = {}
	cur_union = {}
	cur_struct = {}
	cur_func_name = ''
	cur_enum_name = ''
	cur_union_name = ''
	cur_struct_name = ''
	all_enum_names = set()
	all_enum_values = {}
	all_const_values = {}
	all_struct_names = set()
	must_alias = {
		'int8_t': 'i8',
		'int16_t': 'i16',
		'int32_t': 'i32',
		'int64_t': 'i64',
		'uint8_t': 'u8',
		'uint16_t': 'u16',
		'uint32_t': 'u32',
		'uint64_t': 'u64',
		'size_t': 'usize',
		'char': 'i8',
		'signed char': 'i8',
		'unsigned char': 'u8',
		'short': 'i16',
		'signed short': 'i16',
		'unsigned short': 'u16',
		'int': 'i32',
		'signed int': 'i32',
		'unsigned': 'u32',
		'unsigned int': 'u32',
		'long': 'i64',
		'signed long': 'i64',
		'unsigned long': 'u64',
		'long long': 'i64',
		'signed long long': 'i64',
		'unsigned long long': 'u64',
		'float': 'f32',
		'double': 'f64',
		'const char*': "*const i8",
	}
	try:
		metadata = ret['metadata']
		all_enum_names |= set(metadata['all_enum_names'])
		all_enum_values = metadata['all_enum_values']
		all_const_values = metadata['all_const_values']
		all_struct_names |= set(metadata['all_struct_names'])
		must_alias |= metadata['must_alias']
	except KeyError:
		pass
	enabled = False
	if is_include_header:
		enabled = True
	last_line = ''
	echo_indent = '    ' * is_include_header
	with open(input, 'r') as f:
		for line in f:
			if is_multiline_comment:
				if '*/' in line:
					line = line.split('*/', 1)[1].lstrip()
					is_multiline_comment = False
				else:
					continue
			while '/*' in line:
				if '*/' in line:
					left, right = line.split('/*', 1)
					line = left.rstrip() + ' ' + right.split('*/', 1)[1].lstrip()
				else:
					line = line.split('/*', 1)[0].rstrip()
					is_multiline_comment = True
			line = line.split('//', 1)[0].rstrip()
			trimmed_line = line.lstrip()
			indent = len(line) - len(trimmed_line)
			line = (last_line + ' ' + trimmed_line).lstrip()
			last_line = ''
			if line is None or len(line) == 0:
				continue
			if line.endswith('\\'):
				last_line += line[:-1]
				continue
			if line.startswith(('#ifdef ', '#ifndef ')):
				sharp_if_level += 1
				if line.startswith('#ifndef VK_NO_PROTOTYPES'):
					is_proto = True
				elif line.startswith('#ifdef __cplusplus'):
					is_cpp = True
				continue
			if line.startswith("#else"):
				continue
			if line.startswith('#endif'):
				sharp_if_level -= 1
				if sharp_if_level <= 1:
					is_proto = False
					is_cpp = False
				continue
			if line.startswith('#include'):
				print(echo_indent, end='')
				print(line)
				if '<' in line or '>' in line:
					continue
				include_file = line.split('"', 2)[1]
				include_path = os.path.dirname(include_file)
				include_file = os.path.basename(include_file)
				if include_file == 'vk_platform.h':
					print(echo_indent, end='')
					print('Skipped: "vk_platform.h"')
					continue
				with pushd(include_path):
					ret['metadata'] = {
						'all_enum_names': all_enum_names,
						'all_enum_values': all_enum_values,
						'all_const_values': all_const_values,
						'all_struct_names': all_struct_names,
						'must_alias': must_alias,
					}
					parsed = parse(include_file, ret, is_include_header + 1)
					metadata = parsed['metadata'].copy()
					del parsed['metadata']
					ret |= parsed
					all_enum_names |= set(metadata['all_enum_names'])
					all_enum_values |= metadata['all_enum_values']
					all_const_values |= metadata['all_const_values']
					all_struct_names |= set(metadata['all_struct_names'])
					must_alias |= metadata['must_alias']
				continue
			if enabled == False:
				if line.startswith('#define VK_VERSION_1_0 1'):
					enabled = True
				else:
					continue
			if line.startswith(('#define VK_', '#define vulkan_')) and line.endswith(' 1') and indent == 0 and '_SPEC_VERSION ' not in line:
				cur_ver = line.split(' ', 2)[1];
				ret[cur_ver] = {
					'typedefs': {},
					'handles': [],
					'non_dispatchable_handles': [],
					'constants': {},
					'enums': {},
					'unions': {},
					'structs': {},
					'funcs': [],
					'func_protos': {},
				}
				if cur_ver == 'VK_VERSION_1_0':
					for type, alias in must_alias.items():
						if ' ' not in type and '*' not in type:
							ret[cur_ver]['typedefs'][type] = alias
			if is_cpp:
				print(echo_indent, end='')
				print(f'Skip cpp code: {line}')
				continue
			if line.startswith('#define ') and line.endswith('_H_ 1'):
				print(echo_indent, end='')
				print(line)
				continue
			if cur_ver == '':
				print(echo_indent, end='')
				print(f'Unversioned line: {line}')
				continue
			if line.startswith('#define '):
				parts = line.split(' ', 2)
				ident, value = parts[1], parts[2].strip()
				if '(' in ident or ')' in ident or ident.endswith(('_SPEC_VERSION', '_EXTENSION_NAME')):
					continue
				while f'{value[0]}{value[-1]}' == '()':
					value = value[1:-1]
				def try_redir(ident):
					ident = ident.strip()
					try:
						val = all_const_values[ident]
					except KeyError:
						val = ident
					return int(val)
				def vk_make_version(major_minor_patch):
					major, minor, patch = major_minor_patch.split('(', 1)[1].split(')', 1)[0].split(',')
					major, minor, patch = try_redir(major), try_redir(minor), try_redir(patch)
					return hex((major << 22) | (minor << 12) | patch)
				def vk_make_api_version(variant_major_minor_patch):
					variant, major, minor, patch = variant_major_minor_patch.split('(', 1)[1].split(')', 1)[0].split(',')
					variant, major, minor, patch = try_redir(variant), try_redir(major), try_redir(minor), try_redir(patch)
					return hex((variant << 29) | (major << 22) | (minor << 12) | patch)
				def vk_make_video_std_version(major_minor_patch):
					major, minor, patch = major_minor_patch.split('(', 1)[1].split(')', 1)[0].split(',')
					major, minor, patch = try_redir(major), try_redir(minor), try_redir(patch)
					return hex((major << 22) | (minor << 12) | patch)
				if value.startswith('VK_MAKE_VERSION'):
					value = vk_make_version(value[len('VK_MAKE_VERSION'):])
				elif value.startswith('VK_MAKE_API_VERSION'):
					value = vk_make_api_version(value[len('VK_MAKE_API_VERSION'):])
				elif value.startswith('VK_MAKE_VIDEO_STD_VERSION'):
					value = vk_make_video_std_version(value[len('VK_MAKE_VIDEO_STD_VERSION'):])
				if ident != cur_ver:
					ret[cur_ver]['constants'][ident] = value
					all_const_values |= {ident: value}
				continue
			if is_enum:
				if line.startswith('}'):
					is_enum = False
					ret[cur_ver]['enums'][cur_enum_name] = cur_enum
					cur_enum = {}
					continue
				if '=' in line:
					if line.endswith(','):
						line = line[:-1]
					name, value = line.split('=', 1)
					cur_enum |= {name.strip(): value.strip()}
					all_enum_values |= {name.strip(): [value.strip(), cur_enum_name]}
				else:
					print(echo_indent, end='')
					print(f'Unknown data in enum: "{line}"')
				continue
			elif is_union:
				if line.startswith('}'):
					is_union = False
					ret[cur_ver]['unions'][cur_union_name] = cur_union
					cur_union = {}
					continue
				if line.endswith(';'):
					line = line[:-1]
					type, name = line.rsplit(' ', 1)
					cur_union |= {name.strip(): type.strip()}
				else:
					print(echo_indent, end='')
					print(f'Unknown data in union: "{line}"')
				continue
			elif is_struct:
				while ' :' in line or ': ' in line:
					line = line.replace(' :', ':').replace(': ', ':')
				if line.startswith('}'):
					is_struct = False
					ret[cur_ver]['structs'][cur_struct_name] = cur_struct
					cur_struct = {}
					continue
				if line.endswith(';'):
					line = line[:-1]
					type, name = line.rsplit(' ', 1)
					cur_struct |= {name.strip(): type.strip()}
				else:
					print(echo_indent, end='')
					print(f'Unknown data in struct: "{line}"')
				continue
			elif is_proto:
				if line.startswith('VKAPI_ATTR '):
					if line.endswith('('):
						ret[cur_ver]['funcs'] += [line[:-1].rsplit(' ', 1)[-1]]
					else:
						print(echo_indent, end='')
						print(f'Unknown data in function declaration: "{line}"')
				continue
			elif is_typedef_func:
				if line.endswith(');'):
					is_typedef_func = False
					line = line[:-2]
				elif line.endswith(','):
					line = line[:-1]
				for param in line.split(','):
					param_type, param_name = param.rsplit(' ', 1)
					cur_func['params'] |= {param_name.strip(): param_type.strip()}
				if is_typedef_func == False:
					ret[cur_ver]['func_protos'][cur_func_name] = cur_func.copy()
					cur_func = {}
			else:
				if line.startswith('typedef enum '):
					is_enum = True
					cur_enum_name = line[len('typedef enum '):].split(' ', 1)[0]
					cur_enum = {}
					all_enum_names |= {cur_enum_name}
					continue
				if line.startswith('typedef union '):
					is_union = True
					cur_union_name = line[len('typedef union '):].split(' ', 1)[0]
					cur_union = {}
					continue
				if line.startswith('typedef struct '):
					is_struct = True
					cur_struct_name = line[len('typedef struct '):].split(' ', 1)[0]
					cur_struct = {}
					all_struct_names |= {cur_enum_name}
					continue
				if line.startswith('typedef '):
					if 'VKAPI_PTR' in line:
						cur_func_name = line.split('VKAPI_PTR *', 1)[1].split(')', 1)[0]
						if line.endswith('('):
							is_typedef_func = True
							params = {}
						elif line.endswith(');'):
							params = {}
							for param in line.split(f'{cur_func_name})(', 1)[1].rsplit(')', 1)[0].split(','):
								if param == 'void':
									pass
								elif ' ' in param:
									type, name = param.rsplit(' ', 1)
									params |= {name.strip(): type.strip()}
								else:
									params |= {f'_param_{params.len()}': type.strip()}
						else:
							print(echo_indent, end='')
							print(f'Unknown data in function prototype: "{line}"')
							continue
						cur_func = {
							'ret_type': line[len('typedef '):].split('(', 1)[0].strip(),
							'params': params,
						}
						if is_typedef_func == False:
							ret[cur_ver]['func_protos'][cur_func_name] = cur_func.copy()
							cur_func = {}
					else:
						if line.endswith(';'):
							line = line[:-1]
							type, name = line[len('typedef '):].rsplit(' ', 1)
							ret[cur_ver]['typedefs'] |= {name: type}
						else:
							print(echo_indent, end='')
							print(f'Unknown data in typedef: "{line}"')
					continue
				if line.startswith('VK_DEFINE_HANDLE'):
					handle_name = line.split('(', 1)[1].split(')', 1)[0]
					ret[cur_ver]['handles'] += [handle_name]
					continue
				if line.startswith('VK_DEFINE_NON_DISPATCHABLE_HANDLE'):
					handle_name = line.split('(', 1)[1].split(')', 1)[0]
					ret[cur_ver]['non_dispatchable_handles'] += [handle_name]
					continue
	ret['metadata'] = {
		'all_enum_names': list(all_enum_names),
		'all_enum_values': all_enum_values,
		'all_const_values': all_const_values,
		'all_struct_names': list(all_struct_names),
		'must_alias': must_alias,
	}
	return ret

def to_rust(outfile, parsed):
	metadata = parsed['metadata']
	all_enum_names = set(metadata['all_enum_names'])
	all_enum_values = metadata['all_enum_values']
	all_const_values = metadata['all_const_values']
	all_struct_names = set(metadata['all_struct_names'])
	must_alias = metadata['must_alias']
	def ctype_to_rust(ctype):
		ctype = ctype.replace(' *', '*')
		try:
			rust = must_alias[ctype]
			ctype = ''
		except KeyError:
			rust = ''
		while len(ctype):
			if ctype.endswith('const*'):
				ctype = ctype[:-len('const*')].rstrip()
				rust = f'*const {rust}'
			elif ctype.endswith('*'):
				if ctype.startswith('const '):
					ctype = ctype[len('const '):-1]
					rust = f'*const {rust}'
				else:
					ctype = ctype[:-1]
					rust = f'*mut {rust}'
			else:
				if ctype.startswith('struct '):
					ctype = ctype[len('struct '):].strip()
				if ctype == 'void': ctype = 'c_void'
				rust = f'{rust.strip()} {ctype}'.strip()
				break
		return rust
	def process_guts(name, type, is_param = False):
		type = ctype_to_rust(type)
		if type.startswith('const '):
			type = type[len('const '):]
		if '[' in name:
			name, size = name.split('[', 1)
			size = size.split(']', 1)[0]
			type = f'[{type}; {size} as usize]'
			if is_param: type = f'&{type}'
		if name == 'type': name = f'{name}_'
		return name, type
	def process_constant_value(value):
		while True:
			try:
				value = all_const_values[value]
			except KeyError:
				break
		while True:
			try:
				value, source = all_enum_values[value]
			except KeyError:
				break
		type_ = None
		value = value.lower()
		if value.endswith('ull'):
			type_ = 'u64'
			value = f'{value[:-3]}u64'
		elif value.endswith('ll'):
			type_ = 'i64'
			value = f'{value[:-2]}i64'
		elif value.endswith('u'):
			type_ = 'u32'
			value = f'{value[:-1]}u32'
		elif value.endswith('l'):
			type_ = 'i32'
			value = f'{value[:-1]}i32'
		elif value.endswith('f') and '.' in value:
			type_ = 'f32'
			value = f'{value[:-1]}f32'
		if value[0] == '~':
			value = f'!{value[1:]}'
		if type_ is None:
			type_ = 'u32'
		return value, type_
	def union_member_type_process(union, type):
		is_enum = type in all_enum_names
		if is_enum:
			struct.write(f'\t/// Original type: {type}\n');
			type = 'u32'
		try:
			type = must_alias[type]
		except KeyError:
			pass
		return type
	def struct_member_type_process(struct, type):
		is_pointer = type.startswith(('&', '*'))
		is_enum = type in all_enum_names
		if is_pointer:
			struct.write(f'\t/// Original type: {type}\n');
			type = 'usize'
		elif is_enum:
			struct.write(f'\t/// Original type: {type}\n');
			type = 'u32'
		try:
			type = must_alias[type]
		except KeyError:
			pass
		return type
	vk_struct = io.StringIO()
	vk_traits = io.StringIO()
	vk_s_impl = io.StringIO()
	vk_struct.write('#[derive(Default, Debug, Clone)]\n');
	vk_struct.write('pub struct VkCore {\n');
	vk_struct.write(f'\tpub instance: VkInstance,\n')
	vk_struct.write(f'\tpub extensions: BTreeSet<String>,\n')
	vk_s_impl.write('impl VkCore {\n')
	vk_s_impl.write("\tpub fn new(app_info: VkApplicationInfo, mut get_instance_proc_address: impl FnMut(VkInstance, &'static str) -> *const c_void) -> Self {\n")
	vk_s_impl.write('\t\tlet vkEnumerateInstanceExtensionProperties = get_instance_proc_address(null(), "vkEnumerateInstanceExtensionProperties");\n')
	vk_s_impl.write('\t\tif vkEnumerateInstanceExtensionProperties == null() {\n')
	vk_s_impl.write('\t\t\tpanic!("Initialize Vulkan failed: couldn\'t get the address of `vkEnumerateInstanceExtensionProperties()`");\n')
	vk_s_impl.write('\t\t}\n')
	vk_s_impl.write('\t\tlet vkEnumerateInstanceExtensionProperties: PFN_vkEnumerateInstanceExtensionProperties = unsafe{transmute(vkEnumerateInstanceExtensionProperties)};\n')
	vk_s_impl.write('\t\tlet mut count: u32 = 0;\n')
	vk_s_impl.write('\t\tlet err = vkEnumerateInstanceExtensionProperties(null(), &mut count as *mut _, null_mut());\n')
	vk_s_impl.write('\t\tif err != VkResult::VK_SUCCESS {\n')
	vk_s_impl.write('\t\t\tpanic!("Initialize Vulkan failed: couldn\'t get the number of the Vulkan extensions: {err:?}")\n')
	vk_s_impl.write('\t\t}\n')
	vk_s_impl.write('\t\tlet mut extensions: Vec<VkExtensionProperties> = Vec::with_capacity(count as usize);\n')
	vk_s_impl.write('\t\tunsafe {extensions.set_len(count as usize)};\n')
	vk_s_impl.write('\t\tlet err = vkEnumerateInstanceExtensionProperties(null(), &mut count as *mut _, extensions.as_mut_ptr());\n')
	vk_s_impl.write('\t\tif err != VkResult::VK_SUCCESS {\n')
	vk_s_impl.write('\t\t\tpanic!("Initialize Vulkan failed: couldn\'t get the list of the Vulkan extensions: {err:?}")\n')
	vk_s_impl.write('\t\t}\n')
	vk_s_impl.write('\t\tlet extensions: Vec<String> = extensions.into_iter().map(|prop|unsafe {CStr::from_ptr(prop.extensionName.as_ptr())}.to_string_lossy().to_string()).collect();\n')
	vk_s_impl.write('\t\tlet mut c_strings: Vec<CString> = Vec::with_capacity(extensions.len());\n')
	vk_s_impl.write('\t\tfor extension in extensions.iter() {\n')
	vk_s_impl.write('\t\t\tc_strings.push(CString::new(&**extension).unwrap());\n')
	vk_s_impl.write('\t\t}\n')
	vk_s_impl.write('\t\tlet mut ext_pointers: Vec<*const i8> = Vec::with_capacity(extensions.len());\n')
	vk_s_impl.write('\t\tfor (i, _) in extensions.iter().enumerate() {\n')
	vk_s_impl.write('\t\t\text_pointers.push(c_strings[i].as_ptr());\n')
	vk_s_impl.write('\t\t}\n')
	vk_s_impl.write('\t\tlet create_info = VkInstanceCreateInfo {\n')
	vk_s_impl.write('\t\t\tsType: VkStructureType::VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,\n')
	vk_s_impl.write('\t\t\tpNext: null(),\n')
	vk_s_impl.write('\t\t\tflags: 0,\n')
	vk_s_impl.write('\t\t\tenabledLayerCount: 0,\n')
	vk_s_impl.write('\t\t\tpApplicationInfo: &app_info,\n')
	vk_s_impl.write('\t\t\tppEnabledLayerNames: null(),\n')
	vk_s_impl.write('\t\t\tenabledExtensionCount: count,\n')
	vk_s_impl.write('\t\t\tppEnabledExtensionNames: ext_pointers.as_ptr()\n')
	vk_s_impl.write('\t\t};\n')
	vk_s_impl.write('\t\tlet vkCreateInstance = get_instance_proc_address(null(), "vkCreateInstance");\n')
	vk_s_impl.write('\t\tif vkCreateInstance == null() {\n')
	vk_s_impl.write('\t\t\tpanic!("Initialize Vulkan failed: couldn\'t get a valid `vkCreateInstance()` function pointer.")\n')
	vk_s_impl.write('\t\t}\n')
	vk_s_impl.write('\t\tlet vkCreateInstance: PFN_vkCreateInstance = unsafe{transmute(vkCreateInstance)};\n')
	vk_s_impl.write('\t\tlet mut instance: VkInstance = null();\n')
	vk_s_impl.write('\t\tlet result = vkCreateInstance(&create_info, null(), &mut instance);\n')
	vk_s_impl.write('\t\tif result != VkResult::VK_SUCCESS {\n')
	vk_s_impl.write('\t\t\tpanic!("Initialize Vulkan failed: `vkCreateInstance()` failed: {result:?}")\n')
	vk_s_impl.write('\t\t}\n')
	vk_s_impl.write('\t\t\n')
	vk_s_impl.write('\t\tSelf {\n')
	vk_s_impl.write('\t\t\tinstance,\n')
	vk_s_impl.write('\t\t\textensions: extensions.into_iter().collect(),\n')
	def process_version(version, verdata, f):
		nonlocal vk_struct, vk_traits, vk_s_impl
		constants = verdata['constants']
		typedefs = verdata['typedefs']
		handles = verdata['handles']
		non_dispatchable_handles = verdata['non_dispatchable_handles']
		enums = verdata['enums']
		unions = verdata['unions']
		structs = verdata['structs']
		func_protos = verdata['func_protos']
		funcs = verdata['funcs']
		for constant, value in constants.items():
			constval, consttype = process_constant_value(value)
			f.write(f'pub const {constant}: {consttype} = {constval};\n')
		for type, tname in typedefs.items():
			tname = ctype_to_rust(tname)
			f.write(f'pub type {type} = {tname};\n')
		for handle in handles:
			f.write(f'/// Normal handle `{handle}` from {version}\n')
			f.write(f'#[repr(C)] #[derive(Debug, Clone, Copy)] pub struct {handle}_T {{_unused: u32,}}\n')
			f.write(f'pub type {handle} = *const {handle}_T;\n')
		for handle in non_dispatchable_handles:
			f.write(f'/// Non-dispatchable handle `{handle}` from {version}\n')
			f.write(f'#[cfg(target_pointer_width = "32")] pub type {handle} = u64;\n')
			f.write(f'#[cfg(target_pointer_width = "64")] #[repr(C)] #[derive(Debug, Clone, Copy)] pub struct {handle}_T {{_unused: u32,}}\n')
			f.write(f'#[cfg(target_pointer_width = "64")] pub type {handle} = *const {handle}_T;\n')
		for enum, enumpair in enums.items():
			already_values = {}
			asso = io.StringIO()
			f.write('#[repr(C)]\n')
			f.write('#[derive(Debug, Clone, Copy, PartialEq)]\n')
			f.write(f'pub enum {enum} {{\n')
			for enumname, enumval in enumpair.items():
				try:
					enumdef, enumfrom = all_enum_values[enumval]
					asso.write(f'\tpub const {enumname}: {enumfrom} = {enumfrom}::{enumval};\n')
				except KeyError:
					enumval, valtype = process_constant_value(enumval)
					try:
						enumalias = already_values[enumval]
						asso.write(f'\tpub const {enumname}: {enum} = {enum}::{enumalias};\n')
					except KeyError:
						f.write(f'\t{enumname} = {enumval},\n')
						already_values |= {enumval: enumname}
			f.write('}\n')
			asso = asso.getvalue()
			if len(asso):
				f.write(f'impl {enum} {{\n')
				f.write(asso)
				f.write('}\n')
			asso = None
		for union_name, union_guts in unions.items():
			f.write('#[repr(C)]\n')
			f.write('#[derive(Clone, Copy)]\n')
			f.write(f'pub union {union_name} {{\n')
			for name, type in union_guts.items():
				name, type = process_guts(name, type)
				f.write(f'\tpub {name}: {type},\n')
			f.write('}\n')
			f.write(f'impl Debug for {union_name} {{\n')
			f.write('\tfn fmt(&self, f: &mut Formatter) -> fmt::Result {\n')
			f.write(f'\t\tf.debug_struct("{union_name}")\n')
			for name, type in union_guts.items():
				name = name.split('[', 1)[0]
				f.write(f'\t\t.field("{name}", unsafe {{&self.{name}}})\n')
			f.write('\t\t.finish()\n')
			f.write('\t}\n')
			f.write('}\n')
		for struct_name, struct_guts in structs.items():
			has_bitfield = False
			num_bitfields = 0
			last_bits = 0
			struct = io.StringIO()
			s_impl = io.StringIO()
			struct.write('#[repr(C)]\n')
			struct.write('#[derive(Debug, Clone, Copy)]\n')
			struct.write(f'pub struct {struct_name} {{\n')
			for name, type in struct_guts.items():
				name, type = process_guts(name, type)
				if ':' in name:
					if has_bitfield == False:
						has_bitfield = True
						num_bitfields = 1
						s_impl.write(f'impl {struct_name} {{\n')
					name, bits = name.split(':', 1)
					bits = int(bits)
					bf_name = f'bitfield{num_bitfields}'
					struct.write(f'\t/// Bitfield: {name}: {type} in {bits} bits\n')
					s_impl.write(f'\tpub fn get_{name}(&self) -> u32 {{\n')
					s_impl.write(f'\t\t(self.{bf_name} >> {last_bits}) & {hex((1 << bits) - 1)}\n')
					s_impl.write('\t}\n')
					s_impl.write(f'\tpub fn set_{name}(&mut self, value: u32) {{\n')
					s_impl.write(f'\t\tself.{bf_name} = (value & {hex((1 << bits) - 1)}) << {last_bits};\n')
					s_impl.write('\t}\n')
					last_bits += bits
					last_bits %= 32
					if last_bits == 0:
						struct.write(f'\t{bf_name}: u32,\n')
						num_bitfields += 1
				else:
					if last_bits:
						bf_name = f'bitfield{num_bitfields}'
						struct.write(f'\tpub {bf_name}: u32,\n')
						num_bitfields += 1
						last_bits = 0;
					struct.write(f'\tpub {name}: {type},\n')
			if last_bits:
				bf_name = f'bitfield{num_bitfields}'
				struct.write(f'\tpub {bf_name}: u32,\n')
			struct.write('}\n')
			if has_bitfield:
				s_impl.write('}\n')
			f.write(struct.getvalue());
			f.write(s_impl.getvalue());
		for functype_name, func_data in func_protos.items():
			f.write(f'type {functype_name} = extern "system" fn(');
			params = []
			for param_name, param_type in func_data['params'].items():
				param_name, param_type = process_guts(param_name, param_type, is_param = True)
				params += [f'{param_name}: {param_type}']
			f.write(', '.join(params))
			ret_type = func_data["ret_type"]
			if ret_type == 'void':
				f.write(f');\n')
			else:
				f.write(f') -> {ctype_to_rust(ret_type)};\n')
		dummys = io.StringIO()
		traits = io.StringIO()
		struct = io.StringIO()
		t_impl = io.StringIO()
		d_impl = io.StringIO()
		s_impl = io.StringIO()
		struct_version = f'Vulkan_{version.split("_", 1)[-1]}'
		snake_version = to_snake(version)
		traits.write(f'pub trait {version}: Debug {{')
		struct.write(f'#[derive(Debug, Clone, Copy)]\n')
		struct.write(f'pub struct {struct_version} {{')
		t_impl.write(f'impl {version} for {struct_version} {{')
		d_impl.write(f'impl Default for {struct_version} {{\n')
		d_impl.write('\tfn default() -> Self {\n')
		s_impl.write(f'impl {struct_version} {{\n')
		vk_struct.write(f'\tpub {snake_version}: {struct_version},\n')
		vk_traits.write(f'impl {version} for VkCore {{')
		vk_s_impl.write(f'\t\t\t{snake_version}: {struct_version}::new(instance, &mut get_instance_proc_address),\n')
		snakes = {}
		if len(funcs):
			traits.write('\n')
			vk_traits.write('\n')
			s_impl.write("\tpub fn new(instance: VkInstance, mut get_instance_proc_address: impl FnMut(VkInstance, &'static str) -> *const c_void) -> Self {\n")
			s_impl.write('\t\tSelf {\n')
			d_impl.write('\t\tSelf {\n')
			t_impl.write('\n')
			struct.write('\n')
		else:
			s_impl.write("\tpub fn new(_instance: VkInstance, _get_instance_proc_address: impl FnMut(VkInstance, &'static str) -> *const c_void) -> Self {\n")
			s_impl.write('\t\tSelf {')
			d_impl.write('\t\tSelf {')
		for func in funcs:
			func_snake = to_snake(func)
			snakes[func_snake] = func
			func_data = func_protos[f'PFN_{func}']
			params = []
			params_dummy = []
			param_call = []
			for param_name, param_type in func_data['params'].items():
				param_name, param_type = process_guts(param_name, param_type, is_param = True)
				params += [f'{param_name}: {param_type}']
				params_dummy += [f'_: {param_type}']
				param_call += [param_name]
			dummys.write(f'extern "system" fn dummy_{func}({", ".join(params_dummy)})')
			traits.write(f'\tfn {func}(&self, {", ".join(params)})')
			t_impl.write(f'\tfn {func}(&self, {", ".join(params)})')
			vk_traits.write(f'\tfn {func}(&self, {", ".join(params)})')
			d_impl.write(f'\t\t\t{func_snake}: dummy_{func},\n');
			s_impl.write(f'\t\t\t{func_snake}: {{let proc = get_instance_proc_address(instance, "{func}"); if proc == null() {{dummy_{func}}} else {{unsafe {{transmute(proc)}}}}}},\n')
			ret_type = func_data["ret_type"]
			if ret_type == 'void':
				dummys.write(' {\n')
				traits.write(';\n')
				t_impl.write(' {\n')
				vk_traits.write(' {\n')
			elif ret_type == 'VkResult':
				dummys.write(f' -> {ctype_to_rust(ret_type)} {{\n')
				traits.write(f' -> Result<(), VkResult>;\n')
				t_impl.write(f' -> Result<(), VkResult> {{\n')
				vk_traits.write(f' -> Result<(), VkResult> {{\n')
			else:
				dummys.write(f' -> {ctype_to_rust(ret_type)} {{\n')
				traits.write(f' -> {ctype_to_rust(ret_type)};\n')
				t_impl.write(f' -> {ctype_to_rust(ret_type)} {{\n')
				vk_traits.write(f' -> {ctype_to_rust(ret_type)} {{\n')
			dummys.write(f'\tpanic!("Vulkan function pointer of `{func}()` is NULL");\n');
			dummys.write('}\n')
			if ret_type == 'VkResult':
				t_impl.write(f'\t\tvk_convert_result((self.{func_snake})({", ".join(param_call)}))\n')
				vk_traits.write(f'\t\tvk_convert_result((self.{snake_version}.{func_snake})({", ".join(param_call)}))\n')
			else:
				t_impl.write(f'\t\t(self.{func_snake})({", ".join(param_call)})\n')
				vk_traits.write(f'\t\t(self.{snake_version}.{func_snake})({", ".join(param_call)})\n')
			t_impl.write('\t}\n')
			vk_traits.write('\t}\n')
			struct.write(f'\t{func_snake}: PFN_{func},\n')
		traits.write('}\n')
		struct.write('}\n')
		t_impl.write('}\n')
		if len(funcs):
			d_impl.write('\t\t}\n')
			s_impl.write('\t\t}\n')
		else:
			d_impl.write('}\n')
			s_impl.write('}\n')
		s_impl.write('\t}\n')
		s_impl.write('}\n')
		d_impl.write('\t}\n')
		d_impl.write('}\n')
		vk_traits.write('}\n')
		f.write(dummys.getvalue())
		f.write(traits.getvalue())
		f.write(struct.getvalue())
		f.write(t_impl.getvalue())
		f.write(d_impl.getvalue())
		f.write(s_impl.getvalue())
	with open(outfile, 'w') as f:
		f.write('\n')
		f.write('#![allow(dead_code)]\n')
		f.write('#![allow(non_snake_case)]\n')
		f.write('#![allow(non_camel_case_types)]\n')
		f.write('#![allow(non_upper_case_globals)]\n')
		f.write('\n')
		f.write('use std::{\n')
		f.write('\tcollections::BTreeSet,\n')
		f.write('\tffi::{c_void, CStr, CString},\n')
		f.write('\tfmt::{self, Debug, Formatter},\n')
		f.write('\tmem::transmute,\n')
		f.write('\tptr::{null, null_mut},\n')
		f.write('};\n')
		f.write('\n')
		f.write('pub fn vk_make_version(major: u32, minor: u32, patch: u32) -> u32 {\n')
		f.write('\t(major << 22) | (minor << 12) | patch\n')
		f.write('}\n')
		f.write('pub fn vk_make_api_version(variant: u32, major: u32, minor: u32, patch: u32) -> u32 {\n')
		f.write('\t(variant << 29) | (major << 22) | (minor << 12) | patch\n')
		f.write('}\n')
		f.write('pub fn vk_make_video_std_version(major: u32, minor: u32, patch: u32) -> u32 {\n')
		f.write('\t(major << 22) | (minor << 12) | patch\n')
		f.write('}\n')
		f.write('\n')
		f.write('pub fn vk_convert_result(result: VkResult) -> Result<(), VkResult> {\n')
		f.write('\tmatch result {\n')
		f.write('\t\tVkResult::VK_SUCCESS => Ok(()),\n')
		f.write('\t\t_ => Err(result),\n')
		f.write('\t}\n')
		f.write('}\n')
		f.write('\n')
		for version, verdata in parsed.items():
			if version == 'metadata':
				continue
			process_version(version, verdata, f)
		vk_struct.write('}\n')
		vk_s_impl.write('\t\t}\n')
		vk_s_impl.write('\t}\n')
		vk_s_impl.write('}\n')
		f.write(vk_struct.getvalue())
		f.write(vk_traits.getvalue())
		f.write(vk_s_impl.getvalue())


if __name__ == '__main__':
	parsed = parse('vulkan_core.h')
	with open('vkcore.json', 'w') as f:
		json.dump(parsed, f, indent=4)
	to_rust('vkcore.rs', parsed)
