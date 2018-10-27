import sys
import numpy as np
import matplotlib.pyplot as plot
import matplotlib.animation as animation
import mpl_toolkits.mplot3d.axes3d as axes3d

from ..io import audiostream as AudioStream
from ..signal import cortical as cortical

# TODO: put this somewhere else
def cube_marginals(cube, normalize=False):
    """Return 2D marginals for each of three dimensions of a cube of data"""
    c_fcn = np.mean if normalize else np.sum
    xy = c_fcn(cube, axis=2)
    xz = c_fcn(cube, axis=1)
    yz = c_fcn(cube, axis=0)
    return(xy,xz,yz)

class CubePlot:
    """Class for handling creation of cortical cube plots, animations, and movie files"""
    def __init__(self,x,fs=None):

        self.stream = None
        self.x = None
        self.aud = None
        self.cor = None
        self.marginals = None
        self.nX = 0
        self.nY = 0
        self.nZ = 0
        self.N = 0
        self.contours = {}
        self.figure = None
        self.axes = None
        self.fs = None

        if type(x) == str:
            self.stream = AudioStream.AudioStream(x)
            self.fs = self.stream.fs
        else:
            if fs == None: raise Exception, "Must provide sample frequency for audio"
            self.stream = AudioStream.VirtualStream(x,fs)
            self.fs = fs

        #hacky to get the correct shape
        self.process_audio(np.zeros(100))

    def frames(self, verbose=False):
        self.stream.rewind()
        while not self.stream.eof():
            if verbose: sys.stderr.write("Next audio chunk.\n")
            x = self.stream.next()
            if verbose: sys.stderr.write("Loaded %d samples.\n" % len(x))
            self.process_audio(x)
            if verbose: sys.stderr.write("Processed features\n")

            n = self.cor.shape[2]
            (xy,xz,yz) = self.marginals
            for ii in np.arange(n):
                yield (xy[:,:,ii],xz[:,:,ii],yz[:,:,ii])

    def process_audio(self,x):
        (aud,e) = cortical.wav2aud(x,self.fs)
        cor = cortical.aud2cor(aud)
        #reduce time resolution
        #TODO: do this better
        cor = cor[:,:,0::5,:]
        self.aud = aud
        self.cor = cor/(cor.max() or 1)
        self.marginals = cube_marginals(self.cor.transpose((0,1,3,2)),normalize=True)
        (self.nX, self.nY, self.N, self.nZ) = cor.shape


    def eof(self):
        return self.stream.eof()

    def setup_plot(self):
        if self.figure != None and plot.fignum_exists(self.figure.number): plot.close(figure)

        # draw wire cube to aid visualization
        self.figure = plot.figure()
        self.axes = self.figure.gca(projection='3d')

        self.axes.plot([0,self.nX-1,self.nX-1,0,0],[0,0,self.nY-1,self.nY-1,0],[0,0,0,0,0],'k-')
        self.axes.plot([0,self.nX-1,self.nX-1,0,0],[0,0,self.nY-1,self.nY-1,0],[self.nZ-1,self.nZ-1,self.nZ-1,self.nZ-1,self.nZ-1],'k-')
        self.axes.plot([0,0],[0,0],[0,self.nZ-1],'k-')
        self.axes.plot([self.nX-1,self.nX-1],[0,0],[0,self.nZ-1],'k-')
        self.axes.plot([self.nX-1,self.nX-1],[self.nY-1,self.nY-1],[0,self.nZ-1],'k-')
        self.axes.plot([0,0],[self.nY-1,self.nY-1],[0,self.nZ-1],'k-')

        self.axes.set_xlabel("scale")
        self.axes.set_ylabel("rate")
        self.axes.set_zlabel("freq")

        # this appears to be necessary because contourf has buggy behavior when the data range is not exactly (0,1)
        self.axes.set_xlim(0,self.nX-1)
        self.axes.set_ylim(0,self.nY-1)
        self.axes.set_zlim(0,self.nZ-1)

        return self

    def draw_contours(self, xy, xz, yz, plot_front=True):
        if self.figure == None or not plot.fignum_exists(self.figure.number): self.setup_plot()

        alpha = 0.95
        cmap=plot.cm.hot

        xy = xy/xy.max()
        xz = xz/xz.max()
        yz = yz/yz.max()

        x = np.arange(self.nX)
        y = np.arange(self.nY)
        z = np.arange(self.nZ)
        offsets = (self.nZ-1,0,self.nX-1) if plot_front else (0, self.nY-1, 0)
        self.contours["xy"] = self.axes.contourf(x[:,None].repeat(self.nY,axis=1), y[None,:].repeat(self.nX,axis=0), xy, zdir='z', offset=offsets[0], cmap=cmap, alpha=alpha)
        self.contours["xz"] = self.axes.contourf(x[:,None].repeat(self.nZ,axis=1), xz, z[None,:].repeat(self.nX,axis=0), zdir='y', offset=offsets[1], cmap=cmap, alpha=alpha)
        self.contours["yz"] = self.axes.contourf(yz, y[:,None].repeat(self.nZ,axis=1), z[None,:].repeat(self.nY,axis=0), zdir='x', offset=offsets[2], cmap=cmap, alpha=alpha)


    def clear_contours(self):
        # # ref: https://www.mail-archive.com/matplotlib-users@lists.sourceforge.net/msg17614.html
        if self.figure == None or not plot.fignum_exists(self.figure.number): return None
        for plane in self.contours:
            for col in self.axes.collections: #self.contours[plane].collections:
                self.axes.collections.remove(col)

    def plot(self,**kwargs):
        block = kwargs.pop('block') if kwargs.has_key('block') else False
        (xy,xz,yz) = self.marginals
        self.draw_contours(xy.mean(axis=2),xz.mean(axis=2),yz.mean(axis=2))
        plot.show(block=block)

    def write_movie(self, filename = "cortical.mp4", **kwargs):
        if self.figure == None or not plot.fignum_exists(self.figure.number): self.setup_plot()

        FFMpegWriter = animation.writers['ffmpeg']
        metadata = dict(title='Cortical Features', artist='Matplotlib',
            comment='Cortical features')
        writer = FFMpegWriter(fps=20, metadata=metadata)

        with writer.saving(self.figure, filename, 100):
            for frame in self.frames(verbose=True):
                self.clear_contours()
                self.draw_contours(*frame)
                writer.grab_frame()
