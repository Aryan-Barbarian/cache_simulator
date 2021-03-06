import math;

DEFAULT_VALUE = 0;

class LookupResponse(object): #TODO: Make these some non-colliding hashes maybe?
	found = "found"
	not_found_overrode= "not found and overrode an existing entry"
	not_found_no_overrode = "not found and did not override an existing entry"


class Memory(object):


	def __init__(self, address_length=32):
		self.address_length = address_length;
		self.mem = dict() # {32 bit address => value}

	def generate_addresses(self, address, block_offset_size):
		if block_offset_size == 0:
			return list(address)

		address = address[0: (29 - block_offset_size)] # Word addressed
		num_bits = block_offset_size;

		last_num = 0;
		for i in range(num_bits):
			last_num += (1 << i)
		last_num += 1;
		num = 0;

		ans = list();
		while (num != last_num):
			ans.append(address + bin(num)[2:] + "00"); # Get rid of the 0b
			num += 1
		return ans;


	def lookup_one(self, address):

		if address not in self.mem:
			self.mem[address] = DEFAULT_VALUE;

		return self.mem[address]

	def lookup(self, address, block_offset_size):
		ans = [self.lookup_one(addr) for addr in self.generate_addresses(address, block_offset_size)]
		return ans;
	
	def write_many(self, address, values, block_offset_size):
		addresses = self.generate_addresses(address, block_offset_size);
		pairs = [(addresses[i], values[i]) for i in range(len(values))];
		self.write_pairs(pairs)

	def write_pairs(self, address_value_pairs):
		for p in address_value_pairs:
			self.write(p[0], p[1])

	def write(self, address, val):
		self.mem[address] = val;

class Cache(object):
	def __init__(self, cache_size, N_way, bytes_per_entry, memory):

		# Given
		self.memory = memory;
		self.cache_size = cache_size
		self.N_way = N_way
		self.bytes_per_entry = bytes_per_entry

		# Calculating Sizes
		self.num_entries = cache_size / bytes_per_entry # Entries total
		self.num_sets = self.num_entries / N_way
		self.num_ways = self.num_entries / self.num_sets
		self.entries_per_set = self.num_entries / self.num_sets;
		self.blocks_per_entry = self.bytes_per_entry / 4;

		# Address segment sizes
		self.set_index_size = int.bit_length(self.num_sets - 1)
		self.block_offset_size = int.bit_length(self.blocks_per_entry - 1)

		self.sets = dict(); # {Set Index => Set Objects}

		
		# Keeps track of all entries overriden because of conflict misses
		self.overriden_conflict = set()

		# Keeps track of all entries overriden because of capacity misses
		self.overriden_capacity = set()

		self.bytes_written = 0;

		self.num_misses = 0;
		self.compulsory_misses = list();
		self.conflict_misses = list();
		self.capacity_misses = list();

		self.num_hits = 0;

	def is_full(self):
		# TODO: Does this work?
		return self.bytes_written >= self.cache_size;

	def dump_info(self):

		print("Sets: \t" + str(self.num_sets))
		print("Block Offset: \t" + str(self.block_offset_size))
		print("\n\n")
		print("Total Hits: \t" + str(self.num_hits))
		print("Total Misses: \t" + str(self.num_misses))
		print("Hit Rate: \t" + str((self.num_hits) / (1.0 * self.num_hits + self.num_misses) ))
		print("\n")
		print("compulsory misses: \t" + str(len(self.compulsory_misses)))
		print("conflict misses: \t" + str(len(self.conflict_misses)))
		print("capacity misses: \t" + str(len(self.capacity_misses)))
		print("\n")

	"""
	Just breaks an address into its different components (tag, set index, block offset)
	The return type of each of these values is int
	"""
	def tokenize(self, address):
		start = 0
		address = bin(address);
		address = address[2:] # To chop off the 0b....

		address = address[:-2] # Byte offset

		start = self.block_offset_size
		block_offset = int("0" + address[-start:], 2);
		address = address[:-start]

		start = self.set_index_size
		set_addr = int("0" + address[-start:], 2);
		address = address[:-start]

		tag = int("0" + address[:], 2);
		
		return (tag, set_addr, block_offset)

	def write(self, address, val, full=False):
		return self.lookup(address, True, val, full)

	def get_set(self, set_addr):
		if set_addr not in self.sets:
			self.sets[set_addr] = CacheSet(self, set_addr)
		return self.sets[set_addr]

	"""
	It finds the correct set to send the lookup request to.
	Most of the actual cache lookup logic is handled in the set.
	This method mainly keeps track of hits and misses, and keeps
	track of the different types of misses.

	If a value was not found (and thus had to be fetched from memory,)
	this method will check if another value had to be evicted from the cache.
		If yes: It will try to find out why that value had to be evicted.
			If the cache wasn't full, then it must have just been a set collision
			If the cache was full, it must have been a capacity issue.

	After a miss, this method will also try to figure out the cause for that miss.
	If we had never requested that address before, it's obviously a compulsory miss.

	If we had requested that address before, but we don't have it now, then we must
	have had to evict that value at some point. This is either a capacity or conflict miss.

	If we had evicted that value because of a set collision, it's a conflict miss.
	If we had evicted that value because of lack of space in the cache, it's a capacity miss.
	"""
	def lookup(self, address, write=False, write_value=False, full=False):
		tag, set_addr, block_offset = self.tokenize(address);

		(val, response, old_tag) = self.get_set(set_addr).lookup(tag, block_offset, write, write_value)
		if full:
			print("Divided: " + str(tag) + " | " + str(set_addr) + " | " + str(block_offset) + " | 00 ")

		miss_type = "FOUND"
		if response != LookupResponse.found:
			miss_type = "COMPULSORY"
			self.num_misses += 1;
			self.bytes_written += self.bytes_per_entry

			if tag in self.overriden_conflict: 
				self.conflict_misses.append(tag);
				miss_type = "CONFLICT"
			elif tag in self.overriden_capacity: 
				self.capacity_misses.append(tag);
				miss_type = "CAPACITY"
			else:
				self.compulsory_misses.append(tag);

			if response == LookupResponse.not_found_overrode:
				# We overrode something. Capacity miss or conflict miss
				self.bytes_written -= self.bytes_per_entry
				# It's capacity miss iff we were full
				if self.is_full():
					self.overriden_capacity.add(old_tag)
				else:
					self.overriden_conflict.add(old_tag)		
		
		if response == LookupResponse.found:
			self.num_hits += 1

		if full:
			print("Bytes written so far: " + str(self.bytes_written))
			return (val, miss_type, response, old_tag)
		else:
			return val;


class CacheSet(object):

	def __init__(self, cache, set_index):

		self.cache = cache
		self.index_size = cache.set_index_size;
		self.num_ways = cache.num_ways;
		self.index = set_index;


		# Contains CacheEntry objects. len = num_ways
		# Initially all invalid
		self.entries = [CacheEntry(0, self.cache) for i in range(self.num_ways)] 


	"""
	Returns (Value, Lookup Response, address of value that was evicted to make room for this)
	"""
	def lookup(self, tag, block_offset, write=False, write_value=False):
		ans = False;

		for entry in self.entries:
			entry.age += 1
			if entry.tag == tag and entry.valid :
				ans = entry.lookup(block_offset, write, write_value);
				entry.age = 0;
				return ans;

		if not ans:
			# We have not found it, time to replace the least recently used one
			ans = self.ask_memory(self.index, tag, block_offset)
			return ans;

		# Make the entry young again
		# TODO: What if Null? Should be impossible...
		


	def oldest_entry(self):
		ans = (self.entries[0].age, self.entries[0]);
		for entry in self.entries:
			if entry.age <= ans[0]:
				ans = (entry.age, entry)
		return ans[1];

	def ask_memory(self, set_index, tag, block_offset):
		query = str(tag) + str(set_index) + str(block_offset) + "00"

		# vals for that entry. len should be blocks_per_entry
		values = self.cache.memory.lookup(query, self.cache.block_offset_size) 

		# Find the oldest and before we kill it forever, commit its writes to memory
		to_change = self.oldest_entry();

		old_tag = to_change.tag;
		if to_change.written:
			old_query = str(old_tag) + str(set_index) + str(block_offset) + "00"
			self.cache.memory.write_many(old_query, to_change.blocks, self.cache.block_offset_size);

		to_change.blocks = values;
		to_change.tag = tag;
		to_change.age = 0;

		response = LookupResponse.not_found_overrode
		if not to_change.valid:
			to_change.valid = True
			response = LookupResponse.not_found_no_overrode

		val = to_change.lookup(block_offset)[0]
		return (val, response, old_tag);



class CacheEntry(object):

	def __init__(self, tag, cache):
		self.cache = cache;
		self.tag = tag;

		self.blocks = [0 for i in range(cache.blocks_per_entry)] # Will contain values
		self.valid = False;
		self.written = False; 

		self.age = 0; # If age is 0, it's just been used.

	def lookup(self, block_offset, write=False, write_val=False):
		# if self.tag != self.block_offset:
		# 	return (False, LookupResponse.not_found_overrode);
		# 	# Now gotta pull the info?
		if write:
			self.blocks[block_offset] = write_val
			self.written = True

		ans = (self.blocks[block_offset], LookupResponse.found, False);
		return ans;

