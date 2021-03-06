import pysam
import glob, gzip
from itertools import combinations
from os.path import basename


import logging, sys, optparse
from collections import defaultdict
from os.path import join, basename, dirname, isfile


# maximum distance between two variants to get compared
MAXDIST=50
# do we check if the refAllele sequences are really correct?
CHECKREF=False
#CHECKREF=True

# === COMMAND LINE INTERFACE, OPTIONS AND HELP ===
parser = optparse.OptionParser("usage: %prog [options] filenames - find variants in VCF that have a different position but lead to the same sequence. Can process many files at a time.")

parser.add_option("-d", "--debug", dest="debug", action="store_true", help="show debug messages") 
#parser.add_option("-f", "--file", dest="file", action="store", help="run on file") 
#parser.add_option("", "--test", dest="test", action="store_true", help="do something") 
(options, args) = parser.parse_args()

if options.debug:
    logging.basicConfig(level=logging.DEBUG)
else:
    logging.basicConfig(level=logging.INFO)

PATH = "/hive/groups/cgl/brca/phase1/data/cutoff_vcf/"
chr13 = open("brca2.txt", "r")
BRCA2 = chr13.read()
chr17 = open("brca1.txt", "r")
BRCA1 = chr17.read()
BRCA2_START = 32800000
BRCA1_START = 41100000

class FastaReader:
    """ a class to parse a fasta file 
    Example:
        fr = maxbio.FastaReader(filename)
        for (id, seq) in fr.parse():
            print id,seq """

    def __init__(self, fname):
        if hasattr(fname, 'read'):
            self.f = fname
        elif fname=="stdin":
            self.f=sys.stdin
        elif fname.endswith(".gz"):
            self.f=gzip.open(fname)
        else:
            self.f=open(fname)
        self.lastId=None

    def parse(self):
      """ Generator: returns sequences as tuple (id, sequence) """
      lines = []

      for line in self.f:
              if line.startswith("\n") or line.startswith("#"):
                  continue
              elif not line.startswith(">"):
                 lines.append(line.replace(" ","").strip())
                 continue
              else:
                 if len(lines)!=0: # on first >, seq is empty
                       faseq = (self.lastId, "".join(lines))
                       self.lastId=line.strip(">").strip()
                       lines = []
                       yield faseq
                 else:
                       if self.lastId!=None:
                           sys.stderr.write("warning: when reading fasta file: empty sequence, id: %s\n" % line)
                       self.lastId=line.strip(">").strip()
                       lines=[]

      # if it's the last sequence in a file, loop will end on the last line
      if len(lines)!=0:
          faseq = (self.lastId, "".join(lines))
          yield faseq
      else:
          yield (None, None)


def main(args, options):
    fnames = args
    dbs = []
    for fname in fnames:
        dbName, vars = readDb(fname)
        dbs.append( (dbName, vars) )
        print "Unique variants in %s:%d" %(dbName, len(vars))

    for db1, db2 in combinations(dbs, 2):
        get_overlap(db1, db2)

def readDb(fname):
    " return vcf as (dbName, dict (chrom, pos, ref, alt) -> desc "
    db_name = basename(fname).split(".")[0]
    if fname.endswith(".gz"):
        varFile = gzip.open(fname, "r")
    else:
        varFile = open(fname, "r")
    variants = defaultdict(list)
    for line in varFile:
        if line.startswith("#"):
            continue
        chrom, pos, varId, ref, alt = line.strip().split("\t")[:5]
        # skip variants that don't lead to change
        if ref==alt:
            continue
        alts = alt.split(",")
        for alt in alts:
            variants[ (chrom, int(pos), ref, alt) ] = (chrom, pos, varId, ref, alt)
    return db_name, variants

def get_overlap(db1, db2):
    " print variants that are different but lead to same sequence "
    db1Name, db1Vars = db1
    db2Name, db2Vars = db2
    for var1, desc1 in db1Vars.iteritems():
        for var2, desc2 in db2Vars.iteritems():

            # don't compare if diff chromosome or start position too far away
            if var1[0]!=var2[0] or abs(var1[1]-var2[1]) > MAXDIST :
                continue

            if var1!=var2:
                seq1, seq2, fullSeq = variant_seqs(var1, var2)
                if seq1 is None:
                    continue
                if seq1==seq2:
                    chr1, pos1, id1, from1, to1 = desc1
                    chr2, pos2, id2, from2, to2 = desc2
                    pretty1 = "%s:%s->%s (%s)" % (int(pos1), from1, to1, id1)
                    pretty2 = "%s:%s->%s (%s)" % (int(pos2), from2, to2, id2)
                    print "%s-%s:" % (db1Name, db2Name), pretty1, "/", pretty2, fullSeq

    #print "overlap between the %s and %s: %d" %(name_db1, name_db2, num_overlap)


def variant_seqs(v1, v2):
    " return (edited1, edited2) "
    chr1, pos1, ref1, alt1 = v1
    chr2, pos2, ref2, alt2 = v2
    pos1 = int(pos1)
    pos2 = int(pos2)
    # make sure that v1 is upstream of v2
    if pos1 > pos2:
        #(chr1, pos1, ref1, alt1 ), (chr2, pos2, ref2, alt2 ) = (chr2, pos2, ref2, alt2), (chr1, pos1, ref1, alt1)
        return variant_seqs(v2, v1)

    # lift coordinates and make everything 0-based
    if chr1 == "13":
        seq = BRCA2
        pos1 = pos1 -1 - BRCA2_START
        pos2 = pos2 -1 - BRCA2_START
    elif chr1 == "17":
        seq = BRCA1
        pos1 = pos1 - 1 - BRCA1_START
        pos2 = pos2 - 1 - BRCA1_START
    else:
        assert(False)

    assert(pos1>0)
    assert(pos2>0)
    assert(pos1 < 200000)
    assert(pos2 < 200000)
    assert(len(ref1)!=0)
    assert(len(ref2)!=0)
    if len(ref2)>100 or len(ref1)>100:
        return None, None, None

    # replace vcf ref string with alt string
    if CHECKREF:
        genomeRef1 = seq[pos1:pos1+len(ref1)].upper()
        genomeRef2 = seq[pos2:pos2+len(ref2)].upper()
        if (genomeRef1!=ref1):
            print "ref1 is not in genome", genomeRef1, ref1
        if (genomeRef2!=ref2):
            print "ref2 is not in genome", genomeRef2, ref2
        assert(genomeRef1==ref1)
        assert(genomeRef2==ref2)

    edited_v1 = seq[0:pos1]+alt1+seq[pos1+len(ref1):]
    edited_v2 = seq[0:pos2]+alt2+seq[pos2+len(ref2):]
    fullSeq = seq[min(pos1,pos2):max(pos1+len(ref1),pos1+len(alt1),pos2+len(alt2),pos2+len(ref2))]
    return edited_v1, edited_v2, fullSeq

if __name__ == "__main__":
    main(args, options)
