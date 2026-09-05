#ifndef UDP_THREAD_H
#define UDP_THREAD_H

#include <QThread>
#include <QQueue>
#include <QPixmap>
#include <QMutex>
#include <QMutexLocker>
#include <QWaitCondition>
#include <QUdpSocket>
#include <QHostAddress>

// UDP 接收线程：接收 JPEG 视频帧 → 解码成 QPixmap → 交给 Widget 显示。
// 队列与保存标志均受 _queueMutex 保护，跨线程访问线程安全。
class Udp_Thread : public QThread
{
    Q_OBJECT
public:
    explicit Udp_Thread(QHostAddress ip, QString port, QObject *parent = nullptr);
    ~Udp_Thread();

    bool start_flag;    // 线程工作标志
    bool recv_flag;     // 是否把接收数据计入队列

    void stop();        // 暂停线程
    void go_on();       // 继续线程

    // 线程安全取帧（供 Widget 显示）/ 保存请求 / 取保存结果
    bool has_frame();
    QPixmap take_frame();
    void request_save(const QString &path);
    QString take_save_result();

protected:
    void run();

signals:
    void signal_img();
    void signal_img_saved(const QString &path);

private:
    static constexpr int MAX_FRAMES = 96;   // 待显示帧上限，超出丢弃最旧（防积压）

    QUdpSocket *socket;

    QMutex _queueMutex;          // 保护 _frames / _saveFlag / _savePath / _saveResult
    QQueue<QPixmap> _frames;
    bool _saveFlag = false;
    QString _savePath;
    QString _saveResult;

    QMutex _pauseMutex;          // 暂停/继续
    QWaitCondition _pauseCond;
    bool _paused = false;

private slots:
    void on_udp_ready();
};

#endif // UDP_THREAD_H
